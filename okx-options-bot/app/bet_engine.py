from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app import indicators, options_analysis
from app.config import Settings
from app.db import BetsDB
from app.models import TechnicalSnapshot
from app.okx_client import OKXClient
from app.signal import Bias, evaluate_bias

log = logging.getLogger("okx_options_bot.bet_engine")

FILL_POLL_ATTEMPTS = 5
FILL_POLL_DELAY_SECONDS = 0.3

# Event Contracts settle in USDT and always require isolated margin mode
# plus the speedBump flag for non-post_only orders - these are fixed
# protocol requirements, not configurable trading preferences.
EVENT_TD_MODE = "isolated"
EVENT_SPEED_BUMP = "1"

# Settlement fill subType codes observed on OKX Event Contracts.
SETTLEMENT_WIN_SUBTYPE = "414"
SETTLEMENT_LOSS_SUBTYPE = "415"
SETTLEMENT_SUBTYPES = (SETTLEMENT_WIN_SUBTYPE, SETTLEMENT_LOSS_SUBTYPE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_technical_snapshot(
    client: OKXClient, symbol: str, bar: str, limit: int
) -> TechnicalSnapshot:
    inst_id = f"{symbol}-USDT"
    candles = client.get_candles(inst_id, bar=bar, limit=limit)
    closes = [float(c[4]) for c in candles]

    macd_result = indicators.macd(closes)
    return TechnicalSnapshot(
        inst_id=inst_id,
        spot=closes[-1],
        rsi14=indicators.rsi(closes),
        macd=macd_result.macd if macd_result else None,
        macd_signal=macd_result.signal if macd_result else None,
        macd_histogram=macd_result.histogram if macd_result else None,
        ema9=indicators.ema(closes, 9),
        ema21=indicators.ema(closes, 21),
    )


def _wait_for_fill(client: OKXClient, inst_id: str, ord_id: str) -> dict | None:
    for _ in range(FILL_POLL_ATTEMPTS):
        order = client.get_order(inst_id, ord_id)
        if order and order.get("state") in ("filled", "partially_filled"):
            if float(order.get("accFillSz", 0) or 0) > 0:
                return order
        time.sleep(FILL_POLL_DELAY_SECONDS)
    return None


def _skip(message: str) -> str:
    log.warning(message)
    return message


def select_current_event_market(client: OKXClient, symbol: str) -> dict | None:
    """Picks the BTC/ETH/SOL-UPDOWN-15MIN market whose 15m window is
    currently running: strike already fixed (fixTime set) and not yet
    expired. Falls back to the soonest-expiring live market if none has
    fixed yet (e.g. right at a window boundary)."""
    series_id = f"{symbol}-UPDOWN-15MIN"
    now_ms = time.time() * 1000

    markets = client.get_event_markets(series_id, state="live")
    live = [m for m in markets if float(m.get("expTime") or 0) > now_ms]
    if not live:
        return None

    started = [m for m in live if m.get("fixTime")]
    candidates = started or live
    return min(candidates, key=lambda m: float(m.get("expTime") or 0))


def _close_open_bet(db: BetsDB, client: OKXClient, symbol: str, spot: float) -> str:
    open_bet = db.get_open_bet(symbol)
    if open_bet is None:
        return "no open position"

    if not client.authenticated:
        return _skip(f"OKX API credentials not configured, cannot settle bet #{open_bet['id']}")

    inst_id = open_bet["inst_id"]
    try:
        fills = client.get_fills("EVENTS", inst_id=inst_id)
    except Exception:
        log.exception("Failed to fetch fills for %s", inst_id)
        return _skip(f"could not check settlement for {inst_id}, leaving bet #{open_bet['id']} open")

    settlement = next((f for f in fills if f.get("subType") in SETTLEMENT_SUBTYPES), None)
    if settlement is None:
        return _skip(f"{inst_id} not settled yet, leaving bet #{open_bet['id']} open")

    pnl = float(settlement.get("fillPnl") or 0)
    result = "WIN" if settlement.get("subType") == SETTLEMENT_WIN_SUBTYPE else "LOSS"
    exit_value_usd = open_bet["stake_usd"] + pnl
    exit_price = 1.0 if result == "WIN" else 0.0  # binary contract payout per unit

    db.close_bet(
        open_bet["id"],
        closed_at=_now_iso(),
        exit_price=exit_price,
        exit_spot=spot,
        exit_value_usd=exit_value_usd,
        pnl_usd=pnl,
        result=result,
        exit_order_id=str(settlement.get("ordId") or ""),
    )
    message = f"settled {inst_id}: pnl=${pnl:.2f} ({result})"
    log.info("Closed bet #%s: %s", open_bet["id"], message)
    return message


def _open_new_bet(
    db: BetsDB,
    settings: Settings,
    client: OKXClient,
    symbol: str,
    tech: TechnicalSnapshot,
    bias: Bias,
) -> str:
    if bias.label == "Neutral":
        return "neutral, no trade"

    if not client.authenticated:
        return _skip(f"OKX API credentials not configured, cannot open bet for {symbol}")

    market = select_current_event_market(client, symbol)
    if market is None:
        return _skip(f"no live {symbol}-UPDOWN-15MIN event market, skipping bet")

    inst_id = market["instId"]
    outcome = "yes" if bias.label == "Bullish" else "no"
    stake = settings.stake_for(symbol)

    ack = client.place_market_order(
        inst_id,
        side="buy",
        sz=str(stake),
        td_mode=EVENT_TD_MODE,
        outcome=outcome,
        speed_bump=EVENT_SPEED_BUMP,
    )
    if ack.get("sCode") != "0":
        return _skip(f"entry order rejected for {inst_id}: {ack.get('sMsg')}")

    ord_id = ack.get("ordId")
    filled = _wait_for_fill(client, inst_id, ord_id) if ord_id else None
    if filled is None:
        return _skip(f"entry order {ord_id} for {inst_id} did not fill in time")

    entry_price = float(filled.get("avgPx") or 0)
    entry_sz = float(filled.get("accFillSz") or 0)
    if entry_price <= 0 or entry_sz <= 0:
        return _skip(f"entry fill for {inst_id} has no price/size, skipping bet")

    entry_value_usd = entry_price * entry_sz

    db.open_bet(
        symbol=symbol,
        direction="UP" if outcome == "yes" else "DOWN",
        inst_id=inst_id,
        strike=float(market.get("floorStrike") or 0),
        expiry=str(market.get("expTime") or ""),
        bias_score=bias.score,
        opened_at=_now_iso(),
        entry_price=entry_price,
        entry_spot=tech.spot,
        contracts=entry_sz,
        stake_usd=entry_value_usd,
        entry_order_id=ord_id,
    )
    message = (
        f"opened {bias.label} {inst_id}: {entry_sz:.4f} contracts @ {entry_price:.4f} "
        f"(${entry_value_usd:.2f})"
    )
    log.info("%s (order %s)", message, ord_id)
    return message


def run_symbol(db: BetsDB, client: OKXClient, settings: Settings, symbol: str) -> None:
    tech = build_technical_snapshot(client, symbol, settings.candle_bar, settings.candle_limit)
    uly = f"{symbol}-USD"

    close_msg = _close_open_bet(db, client, symbol, tech.spot)

    # Vanilla options market metrics (IV skew, put/call OI) are used purely
    # as an auxiliary signal input here - the bot trades Event Contracts
    # (UPDOWN-15MIN), not these options.
    opts_metrics = None
    try:
        raw_summary = client.get_opt_summary(uly)
        snapshots = options_analysis.parse_opt_summary(uly, raw_summary)
        if snapshots:
            raw_oi = client.get_open_interest(uly)
            options_analysis.attach_open_interest(snapshots, raw_oi)
            opts_metrics = options_analysis.compute_metrics(uly, snapshots, tech.spot)
    except Exception:
        log.exception("Failed to fetch/compute options metrics for %s", uly)

    bias = evaluate_bias(tech, opts_metrics, threshold=settings.bias_threshold)
    log.info("%s bias=%s score=%d", symbol, bias.label, bias.score)

    open_msg = _open_new_bet(db, settings, client, symbol, tech, bias)

    db.log_activity(
        ts=_now_iso(),
        symbol=symbol,
        bias_label=bias.label,
        bias_score=bias.score,
        message=f"close: {close_msg} | open: {open_msg}",
    )
