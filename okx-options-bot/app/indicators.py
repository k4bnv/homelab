from __future__ import annotations

from dataclasses import dataclass


def ema_series(values: list[float], period: int) -> list[float]:
    """EMA series seeded with an SMA of the first `period` values.

    Returns an empty list if there isn't enough data. Index 0 of the
    result corresponds to values[period - 1].
    """
    if period <= 0 or len(values) < period:
        return []
    k = 2 / (period + 1)
    series = [sum(values[:period]) / period]
    for v in values[period:]:
        series.append(v * k + series[-1] * (1 - k))
    return series


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def rsi(values: list[float], period: int = 14) -> float | None:
    """Wilder's RSI, returns the most recent value (0-100)."""
    if len(values) < period + 1:
        return None

    gains = []
    losses = []
    for prev, cur in zip(values, values[1:]):
        change = cur - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


@dataclass
class MACDResult:
    macd: float
    signal: float
    histogram: float


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> MACDResult | None:
    if slow <= fast:
        raise ValueError("slow period must be greater than fast period")

    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    if not fast_series or not slow_series:
        return None

    # fast_series[0] aligns with values[fast-1]; slow_series[0] aligns with
    # values[slow-1]. Trim the fast series so both start at values[slow-1].
    offset = slow - fast
    fast_aligned = fast_series[offset:]
    macd_line = [f - s for f, s in zip(fast_aligned, slow_series)]

    signal_series = ema_series(macd_line, signal)
    if not signal_series:
        return None

    latest_macd = macd_line[-1]
    latest_signal = signal_series[-1]
    return MACDResult(
        macd=latest_macd,
        signal=latest_signal,
        histogram=latest_macd - latest_signal,
    )
