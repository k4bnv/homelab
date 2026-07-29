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

# Event Contract order books on the demo account have no real liquidity -
# confirmed both via the API (empty order book, canceled market AND limit
# orders) and manually in the OKX app itself. Real order placement isn't
# viable here, so the bot never places one: it records the predicted
# direction and settles it against the contract's own real outcome once
# the 15m window expires, accounted at even money (win = +stake,
# loss = -stake). This measures whether the directional signal itself is
# any good, independent of execution/liquidity concerns.
PAPER_ENTRY_PRICE = 0.5


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
    series_id = f"{symbol}-UPDOWN-15MIN"
    try:
        markets = client.get_event_markets(series_id, inst_id=inst_id)
    except Exception:
        log.exception("Failed to fetch market state for %s", inst_id)
        return _skip(f"could not check settlement for {inst_id}, leaving bet #{open_bet['id']} open")

    market = next((m for m in markets if m.get("instId") == inst_id), None)
    outcome_code = market.get("outcome") if market else None
    if not outcome_code or outcome_code == "0":
        return _skip(f"{inst_id} not settled yet, leaving bet #{open_bet['id']} open")

    actual_direction = "UP" if outcome_code == "1" else "DOWN"
    won = actual_direction == open_bet["direction"]
    stake = open_bet["stake_usd"]
    pnl = stake if won else -stake
    result = "WIN" if won else "LOSS"
    exit_value_usd = stake + pnl
    exit_price = 1.0 if won else 0.0

    db.close_bet(
        open_bet["id"],
        closed_at=_now_iso(),
        exit_price=exit_price,
        exit_spot=spot,
        exit_value_usd=exit_value_usd,
        pnl_usd=pnl,
        result=result,
        exit_order_id=None,
    )
    message = (
        f"settled {inst_id}: actual={actual_direction}, bet={open_bet['direction']} "
        f"-> pnl=${pnl:.2f} ({result})"
    )
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

    existing = db.get_open_bet(symbol)
    if existing is not None:
        return _skip(
            f"bet #{existing['id']} on {existing['inst_id']} still open (not settled), "
            f"skipping new bet"
        )

    market = select_current_event_market(client, symbol)
    if market is None:
        return _skip(f"no live {symbol}-UPDOWN-15MIN event market, skipping bet")

    inst_id = market["instId"]
    direction = "UP" if bias.label == "Bullish" else "DOWN"
    stake = settings.stake_for(symbol)

    db.open_bet(
        symbol=symbol,
        direction=direction,
        inst_id=inst_id,
        strike=float(market.get("floorStrike") or 0),
        expiry=str(market.get("expTime") or ""),
        bias_score=bias.score,
        opened_at=_now_iso(),
        entry_price=PAPER_ENTRY_PRICE,
        entry_spot=tech.spot,
        contracts=1.0,
        stake_usd=stake,
        entry_order_id=None,
    )
    message = f"opened (paper) {bias.label} {direction} {inst_id} (${stake:.2f})"
    log.info(message)
    return message


def run_symbol(db: BetsDB, client: OKXClient, settings: Settings, symbol: str) -> None:
    tech = build_technical_snapshot(client, symbol, settings.candle_bar, settings.candle_limit)
    uly = f"{symbol}-USD"

    close_msg = _close_open_bet(db, client, symbol, tech.spot)

    # Vanilla options market metrics (IV skew, put/call OI) are used purely
    # as an auxiliary signal input here - the bot tracks Event Contracts
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
