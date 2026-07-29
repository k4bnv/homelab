from __future__ import annotations

from app.models import OptionsMetrics, TechnicalSnapshot
from app.signal import Bias


def _fmt(value: float | None, suffix: str = "", digits: int = 2) -> str:
    return f"{value:.{digits}f}{suffix}" if value is not None else "n/a"


def format_message(symbol: str, tech: TechnicalSnapshot, opts: OptionsMetrics | None, bias: Bias) -> str:
    lines = [
        f"<b>{symbol} options 15m digest</b>",
        f"Spot: {_fmt(tech.spot, digits=2)}",
        "",
        "<b>Technicals (15m)</b>",
        f"RSI14: {_fmt(tech.rsi14)}",
        f"MACD hist: {_fmt(tech.macd_histogram, digits=4)}",
        f"EMA9/EMA21: {_fmt(tech.ema9)} / {_fmt(tech.ema21)}",
    ]

    lines.append("")
    if opts:
        atm_iv_pct = opts.atm_iv * 100 if opts.atm_iv is not None else None
        skew_pct = opts.iv_skew_25d * 100 if opts.iv_skew_25d is not None else None
        lines += [
            f"<b>Options ({opts.expiry})</b>",
            f"ATM IV: {_fmt(atm_iv_pct, '%', 1)}",
            f"25d skew (P-C): {_fmt(skew_pct, '%', 2)}",
            f"Put/Call OI ratio: {_fmt(opts.put_call_oi_ratio)}",
            f"OI-wtd Greeks: Δ {_fmt(opts.oi_weighted_delta, digits=3)}  "
            f"Γ {_fmt(opts.oi_weighted_gamma, digits=4)}  "
            f"Θ {_fmt(opts.oi_weighted_theta, digits=3)}  "
            f"V {_fmt(opts.oi_weighted_vega, digits=3)}",
            f"Contracts considered: {opts.contracts_considered}",
        ]
    else:
        lines.append("<b>Options</b>: no live contracts found")

    lines += ["", f"<b>Bias: {bias.label}</b> (score {bias.score:+d})"]
    if bias.reasons:
        lines += [f"- {r}" for r in bias.reasons]

    lines += ["", "Not financial advice. Heuristic signal only."]
    return "\n".join(lines)
