from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from app import indicators, options_analysis
from app.config import Settings
from app.db import BetsDB
from app.models import OptionSnapshot, TechnicalSnapshot
from app.okx_client import OKXClient
from app.signal import Bias, evaluate_bias

log = logging.getLogger("okx_options_bot.bet_engine")

FILL_POLL_ATTEMPTS = 5
FILL_POLL_DELAY_SECONDS = 0.3


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


def contract_usd_value(
    price: float, ct_val: float, ct_val_ccy: str, underlying_symbol: str, spot: float
) -> float:
    """Converts an option premium (per contract, quoted in ct_val_ccy) to USD.

    OKX crypto options can be coin-margined (ct_val_ccy == the underlying
    coin, e.g. BTC) or stable-margined (ct_val_ccy in USD/USDT/USDC).
    """
    ccy = ct_val_ccy.upper()
    if ccy in ("USD", "USDT", "USDC"):
        usd_per_unit = 1.0
    elif ccy == underlying_symbol.upper():
        usd_per_unit = spot
    else:
        raise ValueError(f"Don't know how to convert {ct_val_ccy} to USD")
    return price * ct_val * usd_per_unit


def round_size_to_lot(target_size: float, lot_sz: str, min_sz: str) -> float:
    """Rounds an order size down to a valid multiple of lot_sz, never below min_sz."""
    lot = Decimal(str(lot_sz))
    minimum = Decimal(str(min_sz))
    target = Decimal(str(target_size))

    if lot <= 0:
        return float(max(target, minimum))

    steps = (target / lot).to_integral_value(rounding=ROUND_DOWN)
    rounded = steps * lot
    if rounded < minimum:
        rounded = minimum
    return float(rounded)


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


def _close_open_bet(
    db: BetsDB,
    client: OKXClient,
    settings: Settings,
    symbol: str,
    spot: float,
    inst_by_id: dict,
) -> str:
    open_bet = db.get_open_bet(symbol)
    if open_bet is None:
        return "no open position"

    if not client.authenticated:
        return _skip(f"OKX API credentials not configured, cannot close bet #{open_bet['id']}")

    inst_id = open_bet["inst_id"]
    inst_meta = inst_by_id.get(inst_id)
    if inst_meta is None:
        return _skip(f"no instrument metadata for {inst_id}, leaving bet #{open_bet['id']} open")

    ack = client.place_market_order(
        inst_id, side="sell", sz=str(open_bet["contracts"]), td_mode=settings.okx_td_mode
    )
    if ack.get("sCode") != "0":
        return _skip(
            f"exit order rejected for {inst_id}: {ack.get('sMsg')}, "
            f"leaving bet #{open_bet['id']} open"
        )

    ord_id = ack.get("ordId")
    filled = _wait_for_fill(client, inst_id, ord_id) if ord_id else None
    if filled is None:
        return _skip(
            f"exit order {ord_id} for {inst_id} did not fill in time, "
            f"leaving bet #{open_bet['id']} open"
        )

    exit_price = float(filled.get("avgPx") or 0)
    exit_sz = float(filled.get("accFillSz") or open_bet["contracts"])
    if exit_price <= 0:
        return _skip(f"exit fill for {inst_id} has no price, leaving bet #{open_bet['id']} open")

    ct_val = float(inst_meta.get("ctVal", 1) or 1)
    ct_val_ccy = inst_meta.get("ctValCcy", symbol)
    exit_value_usd = contract_usd_value(exit_price, ct_val, ct_val_ccy, symbol, spot) * exit_sz

    pnl = exit_value_usd - open_bet["stake_usd"]
    result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "PUSH")

    db.close_bet(
        open_bet["id"],
        closed_at=_now_iso(),
        exit_price=exit_price,
        exit_spot=spot,
        exit_value_usd=exit_value_usd,
        pnl_usd=pnl,
        result=result,
        exit_order_id=ord_id,
    )
    message = f"closed {inst_id}: pnl=${pnl:.2f} ({result})"
    log.info("Closed bet #%s %s (order %s)", open_bet["id"], message, ord_id)
    return message


def _open_new_bet(
    db: BetsDB,
    settings: Settings,
    client: OKXClient,
    symbol: str,
    tech: TechnicalSnapshot,
    bias: Bias,
    snapshots: list[OptionSnapshot],
    inst_by_id: dict,
) -> str:
    if bias.label == "Neutral":
        return "neutral, no trade"

    if not client.authenticated:
        return _skip(f"OKX API credentials not configured, cannot open bet for {symbol}")

    opt_type = "C" if bias.label == "Bullish" else "P"
    expiry = options_analysis.nearest_expiry(snapshots)
    if expiry is None:
        return _skip(f"no live option contracts for {symbol}-USD, skipping bet")

    contract = options_analysis.select_atm_contract(snapshots, expiry, opt_type, tech.spot)
    if contract is None:
        return _skip(f"no ATM {opt_type} contract found for {symbol} expiry {expiry}")

    inst_meta = inst_by_id.get(contract.inst_id)
    ticker = client.get_ticker(contract.inst_id)
    if not ticker or not inst_meta:
        return _skip(f"could not fetch entry data for {contract.inst_id}, skipping bet")

    quote_price = float(ticker.get("askPx") or ticker.get("last") or 0)
    if quote_price <= 0:
        # Thin/empty order book (common for less-liquid strikes, especially
        # on demo accounts) - fall back to OKX's model mark price just to
        # size the order. The order itself is still a market order, so this
        # price is an estimate, not a guaranteed fill price.
        mark = client.get_mark_price(contract.inst_id)
        quote_price = float(mark.get("markPx") or 0) if mark else 0
    if quote_price <= 0:
        return _skip(f"no valid quote or mark price for {contract.inst_id}, skipping bet")

    ct_val = float(inst_meta.get("ctVal", 1) or 1)
    ct_val_ccy = inst_meta.get("ctValCcy", symbol)
    usd_per_contract = contract_usd_value(quote_price, ct_val, ct_val_ccy, symbol, tech.spot)
    if usd_per_contract <= 0:
        return _skip(f"non-positive contract value for {contract.inst_id}, skipping bet")

    target_contracts = settings.stake_for(symbol) / usd_per_contract
    sz = round_size_to_lot(
        target_contracts, inst_meta.get("lotSz", "1"), inst_meta.get("minSz", "1")
    )
    if sz <= 0:
        return _skip(f"computed order size is zero for {contract.inst_id}, skipping bet")

    ack = client.place_market_order(
        contract.inst_id, side="buy", sz=str(sz), td_mode=settings.okx_td_mode
    )
    if ack.get("sCode") != "0":
        return _skip(f"entry order rejected for {contract.inst_id}: {ack.get('sMsg')}")

    ord_id = ack.get("ordId")
    filled = _wait_for_fill(client, contract.inst_id, ord_id) if ord_id else None
    if filled is None:
        return _skip(f"entry order {ord_id} for {contract.inst_id} did not fill in time")

    entry_price = float(filled.get("avgPx") or 0)
    entry_sz = float(filled.get("accFillSz") or sz)
    if entry_price <= 0:
        return _skip(f"entry fill for {contract.inst_id} has no price, skipping bet")

    entry_value_usd = (
        contract_usd_value(entry_price, ct_val, ct_val_ccy, symbol, tech.spot) * entry_sz
    )

    db.open_bet(
        symbol=symbol,
        direction="CALL" if opt_type == "C" else "PUT",
        inst_id=contract.inst_id,
        strike=contract.strike,
        expiry=expiry,
        bias_score=bias.score,
        opened_at=_now_iso(),
        entry_price=entry_price,
        entry_spot=tech.spot,
        contracts=entry_sz,
        stake_usd=entry_value_usd,
        entry_order_id=ord_id,
    )
    message = (
        f"opened {bias.label} {contract.inst_id}: {entry_sz:.6f} @ {entry_price:.6f} "
        f"(${entry_value_usd:.2f})"
    )
    log.info("%s (order %s)", message, ord_id)
    return message


def run_symbol(db: BetsDB, client: OKXClient, settings: Settings, symbol: str) -> None:
    tech = build_technical_snapshot(client, symbol, settings.candle_bar, settings.candle_limit)
    uly = f"{symbol}-USD"

    try:
        instruments = client.get_instruments(uly)
    except Exception:
        log.exception("Failed to fetch instruments for %s", uly)
        instruments = []
    inst_by_id = {i["instId"]: i for i in instruments}

    close_msg = _close_open_bet(db, client, settings, symbol, tech.spot, inst_by_id)

    snapshots: list[OptionSnapshot] = []
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

    open_msg = _open_new_bet(db, settings, client, symbol, tech, bias, snapshots, inst_by_id)

    db.log_activity(
        ts=_now_iso(),
        symbol=symbol,
        bias_label=bias.label,
        bias_score=bias.score,
        message=f"close: {close_msg} | open: {open_msg}",
    )
