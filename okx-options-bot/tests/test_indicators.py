from app import indicators


def test_ema_series_length():
    values = list(range(1, 11))  # 1..10
    series = indicators.ema_series(values, period=5)
    assert len(series) == len(values) - 5 + 1
    # seed is SMA of first 5 values: (1+2+3+4+5)/5 = 3
    assert series[0] == 3


def test_ema_not_enough_data_returns_empty():
    assert indicators.ema_series([1, 2, 3], period=5) == []
    assert indicators.ema([1, 2, 3], period=5) is None


def test_rsi_all_gains_is_100():
    values = [float(i) for i in range(1, 20)]  # strictly increasing
    assert indicators.rsi(values, period=14) == 100.0


def test_rsi_all_losses_is_0():
    values = [float(i) for i in range(20, 1, -1)]  # strictly decreasing
    assert indicators.rsi(values, period=14) == 0.0


def test_rsi_flat_series_is_neutral():
    values = [100.0] * 20
    # no gains, no losses -> avg_loss == 0 -> our impl returns 100
    assert indicators.rsi(values, period=14) == 100.0


def test_rsi_needs_period_plus_one_values():
    assert indicators.rsi([1.0, 2.0, 3.0], period=14) is None


def test_macd_requires_enough_data():
    assert indicators.macd([1.0] * 10) is None


def test_macd_returns_result_with_enough_data():
    # enough points for slow(26) + signal(9) EMA chains
    values = [100 + i * 0.5 for i in range(60)]
    result = indicators.macd(values)
    assert result is not None
    assert result.histogram == result.macd - result.signal


def test_macd_invalid_periods_raises():
    try:
        indicators.macd([1.0] * 60, fast=26, slow=12)
        assert False, "expected ValueError"
    except ValueError:
        pass
