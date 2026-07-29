from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptionSnapshot:
    inst_id: str
    uly: str
    expiry: str  # YYMMDD
    strike: float
    opt_type: str  # "C" or "P"
    delta_bs: float
    gamma_bs: float
    theta_bs: float
    vega_bs: float
    mark_vol: float  # implied volatility, e.g. 0.55 == 55%
    oi: float = 0.0


@dataclass
class OptionsMetrics:
    uly: str
    expiry: str
    spot: float
    contracts_considered: int
    atm_iv: float | None
    iv_skew_25d: float | None
    put_call_oi_ratio: float | None
    oi_weighted_delta: float | None
    oi_weighted_gamma: float | None
    oi_weighted_theta: float | None
    oi_weighted_vega: float | None


@dataclass
class TechnicalSnapshot:
    inst_id: str
    spot: float
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    ema9: float | None
    ema21: float | None
