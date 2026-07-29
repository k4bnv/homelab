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


def _close_open_bet(
    db: BetsDB,
    client: OKXClient,
    settings: Settings,
    symbol: str,
    spot: float,
    inst_by_id: dict,
) -> None:
    open_bet = db.get_open_bet(symbol)
    if open_bet is None:
        return

    if not client.authenticated:
        log.warning("OKX API credentials not configured, cannot close bet #%s", open_bet["id"])
        return

    inst_id = open_bet["inst_id"]
    inst_meta = inst_by_id.get(inst_id)
    if inst_meta is None:
        log.warning("No instrument metadata for %s, leaving bet #%s open", inst_id, open_bet["id"])
        return

    ack = client.place_market_order(
        inst_id, side="sell", sz=str(open_bet["contracts"]), td_mode=settings.okx_td_mode
    )
    if ack.get("sCode") != "0":
        log.warning(
            "Exit order rejected for %s: %s, leaving bet #%s open",
            inst_id,
            ack.get("sMsg"),
            open_bet["id"],
        )
        return

    ord_id = ack.get("ordId")
    filled = _wait_for_fill(client, inst_id, ord_id) if ord_id else None
    if filled is None:
        log.warning(
            "Exit order %s for %s did not fill in time, leaving bet #%s open",
            ord_id,
            inst_id,
            open_bet["id"],
        )
        return

    exit_price = float(filled.get("avgPx") or 0)
    exit_sz = float(filled.get("accFillSz") or open_bet["contracts"])
    if exit_price <= 0:
        log.warning("Exit fill for %s has no price, leaving bet #%s open", inst_id, open_bet["id"])
        return

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
    log.info(
        "Closed bet #%s %s: pnl=%.2f (%s), order %s",
        open_bet["id"],
        inst_id,
        pnl,
        result,
        ord_id,
    )


def _open_new_bet(
    db: BetsDB,
    settings: Settings,
    client: OKXClient,
    symbol: str,
    tech: TechnicalSnapshot,
    bias: Bias,
    snapshots: list[OptionSnapshot],
    inst_by_id: dict,
) -> None:
    if bias.label == "Neutral":
        return

    if not client.authenticated:
        log.warning("OKX API credentials not configured, cannot open bet for %s", symbol)
        return

    opt_type = "C" if bias.label == "Bullish" else "P"
    expiry = options_analysis.nearest_expiry(snapshots)
    if expiry is None:
        log.warning("No live option contracts for %s-USD, skipping bet", symbol)
        return

    contract = options_analysis.select_atm_contract(snapshots, expiry, opt_type, tech.spot)
    if contract is None:
        log.warning("No ATM %s contract found for %s expiry %s", opt_type, symbol, expiry)
        return

    inst_meta = inst_by_id.get(contract.inst_id)
    ticker = client.get_ticker(contract.inst_id)
    if not ticker or not inst_meta:
        log.warning("Could not fetch entry data for %s, skipping bet", contract.inst_id)
        return

    quote_price = float(ticker.get("askPx") or ticker.get("last") or 0)
    if quote_price <= 0:
        # Thin/empty order book (common for less-liquid strikes, especially
        # on demo accounts) - fall back to OKX's model mark price just to
        # size the order. The order itself is still a market order, so this
        # price is an estimate, not a guaranteed fill price.
        mark = client.get_mark_price(contract.inst_id)
        quote_price = float(mark.get("markPx") or 0) if mark else 0
    if quote_price <= 0:
        log.warning("No valid quote or mark price for %s, skipping bet", contract.inst_id)
        return

    ct_val = float(inst_meta.get("ctVal", 1) or 1)
    ct_val_ccy = inst_meta.get("ctValCcy", symbol)
    usd_per_contract = contract_usd_value(quote_price, ct_val, ct_val_ccy, symbol, tech.spot)
    if usd_per_contract <= 0:
        log.warning("Non-positive contract value for %s, skipping bet", contract.inst_id)
        return

    target_contracts = settings.stake_usd / usd_per_contract
    sz = round_size_to_lot(
        target_contracts, inst_meta.get("lotSz", "1"), inst_meta.get("minSz", "1")
    )
    if sz <= 0:
        log.warning("Computed order size is zero for %s, skipping bet", contract.inst_id)
        return

    ack = client.place_market_order(
        contract.inst_id, side="buy", sz=str(sz), td_mode=settings.okx_td_mode
    )
    if ack.get("sCode") != "0":
        log.warning("Entry order rejected for %s: %s", contract.inst_id, ack.get("sMsg"))
        return

    ord_id = ack.get("ordId")
    filled = _wait_for_fill(client, contract.inst_id, ord_id) if ord_id else None
    if filled is None:
        log.warning("Entry order %s for %s did not fill in time", ord_id, contract.inst_id)
        return

    entry_price = float(filled.get("avgPx") or 0)
    entry_sz = float(filled.get("accFillSz") or sz)
    if entry_price <= 0:
        log.warning("Entry fill for %s has no price, skipping bet", contract.inst_id)
        return

    entry_value_usd = contract_usd_value(entry_price, ct_val, ct_val_ccy, symbol, tech.spot) * entry_sz

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
    log.info(
        "Opened %s bet on %s: %.6f contracts of %s @ %.6f (order %s, cost $%.2f)",
        bias.label,
        symbol,
        entry_sz,
        contract.inst_id,
        entry_price,
        ord_id,
        entry_value_usd,
    )


def run_symbol(db: BetsDB, client: OKXClient, settings: Settings, symbol: str) -> None:
    tech = build_technical_snapshot(client, symbol, settings.candle_bar, settings.candle_limit)
    uly = f"{symbol}-USD"

    try:
        instruments = client.get_instruments(uly)
    except Exception:
        log.exception("Failed to fetch instruments for %s", uly)
        instruments = []
    inst_by_id = {i["instId"]: i for i in instruments}

    _close_open_bet(db, client, settings, symbol, tech.spot, inst_by_id)

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

    bias = evaluate_bias(tech, opts_metrics)
    log.info("%s bias=%s score=%d", symbol, bias.label, bias.score)

    _open_new_bet(db, settings, client, symbol, tech, bias, snapshots, inst_by_id)
