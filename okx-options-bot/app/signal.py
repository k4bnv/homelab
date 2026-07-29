from __future__ import annotations

from dataclasses import dataclass

from app.models import OptionsMetrics, TechnicalSnapshot


@dataclass
class Bias:
    label: str
    score: int
    reasons: list[str]


def evaluate_bias(tech: TechnicalSnapshot, opts: OptionsMetrics | None) -> Bias:
    """Simple rule-of-thumb heuristic combining momentum + options positioning.

    This is not financial advice: it's a coarse score meant to flag notable
    15m setups worth a human look, not an automated trading signal.
    """
    score = 0
    reasons = []

    if tech.rsi14 is not None:
        if tech.rsi14 <= 30:
            score += 1
            reasons.append(f"RSI14 oversold ({tech.rsi14:.1f})")
        elif tech.rsi14 >= 70:
            score -= 1
            reasons.append(f"RSI14 overbought ({tech.rsi14:.1f})")

    if tech.macd_histogram is not None:
        if tech.macd_histogram > 0:
            score += 1
            reasons.append("MACD histogram positive")
        elif tech.macd_histogram < 0:
            score -= 1
            reasons.append("MACD histogram negative")

    if opts and opts.put_call_oi_ratio is not None:
        if opts.put_call_oi_ratio >= 1.2:
            score -= 1
            reasons.append(f"Put/Call OI ratio high ({opts.put_call_oi_ratio:.2f})")
        elif opts.put_call_oi_ratio <= 0.8:
            score += 1
            reasons.append(f"Put/Call OI ratio low ({opts.put_call_oi_ratio:.2f})")

    if opts and opts.iv_skew_25d is not None:
        if opts.iv_skew_25d >= 0.03:
            score -= 1
            reasons.append(f"25d put skew elevated ({opts.iv_skew_25d:.2%})")
        elif opts.iv_skew_25d <= -0.03:
            score += 1
            reasons.append(f"25d call skew elevated ({opts.iv_skew_25d:.2%})")

    if score >= 1:
        label = "Bullish"
    elif score <= -1:
        label = "Bearish"
    else:
        label = "Neutral"

    return Bias(label=label, score=score, reasons=reasons)
