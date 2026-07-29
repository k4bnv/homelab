from __future__ import annotations

import logging
from datetime import datetime, timezone

from app import indicators, options_analysis
from app.config import Settings
from app.db import BetsDB
from app.models import OptionSnapshot, TechnicalSnapshot
from app.okx_client import OKXClient
from app.signal import Bias, evaluate_bias

log = logging.getLogger("okx_options_bot.bet_engine")


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


def _close_open_bet(
    db: BetsDB, client: OKXClient, symbol: str, spot: float, inst_by_id: dict
) -> None:
    open_bet = db.get_open_bet(symbol)
    if open_bet is None:
        return

    inst_meta = inst_by_id.get(open_bet["inst_id"])
    ticker = client.get_ticker(open_bet["inst_id"])
    if not ticker or not inst_meta:
        log.warning(
            "Could not fetch exit data for %s, leaving bet #%s open",
            open_bet["inst_id"],
            open_bet["id"],
        )
        return

    exit_price = float(ticker.get("bidPx") or ticker.get("last") or 0)
    if exit_price <= 0:
        log.warning(
            "No valid exit price for %s, leaving bet #%s open", open_bet["inst_id"], open_bet["id"]
        )
        return

    ct_val = float(inst_meta.get("ctVal", 1) or 1)
    ct_val_ccy = inst_meta.get("ctValCcy", symbol)
    exit_value_usd = contract_usd_value(exit_price, ct_val, ct_val_ccy, symbol, spot) * open_bet[
        "contracts"
    ]

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
    )
    log.info("Closed bet #%s %s: pnl=%.2f (%s)", open_bet["id"], open_bet["inst_id"], pnl, result)


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

    entry_price = float(ticker.get("askPx") or ticker.get("last") or 0)
    if entry_price <= 0:
        log.warning("No valid entry price for %s, skipping bet", contract.inst_id)
        return

    ct_val = float(inst_meta.get("ctVal", 1) or 1)
    ct_val_ccy = inst_meta.get("ctValCcy", symbol)
    usd_per_contract = contract_usd_value(entry_price, ct_val, ct_val_ccy, symbol, tech.spot)
    if usd_per_contract <= 0:
        log.warning("Non-positive contract value for %s, skipping bet", contract.inst_id)
        return

    contracts = settings.stake_usd / usd_per_contract

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
        contracts=contracts,
        stake_usd=settings.stake_usd,
    )
    log.info(
        "Opened %s bet on %s: %.6f contracts of %s @ %.6f (stake $%.2f)",
        bias.label,
        symbol,
        contracts,
        contract.inst_id,
        entry_price,
        settings.stake_usd,
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

    _close_open_bet(db, client, symbol, tech.spot, inst_by_id)

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
