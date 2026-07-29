from app.models import OptionsMetrics, TechnicalSnapshot
from app.signal import evaluate_bias


def make_tech(rsi14=None, macd_histogram=None):
    return TechnicalSnapshot(
        inst_id="BTC-USDT",
        spot=60000,
        rsi14=rsi14,
        macd=None,
        macd_signal=None,
        macd_histogram=macd_histogram,
        ema9=None,
        ema21=None,
    )


def make_opts(pcr=None, skew=None):
    return OptionsMetrics(
        uly="BTC-USD",
        expiry="250926",
        spot=60000,
        contracts_considered=4,
        atm_iv=0.5,
        iv_skew_25d=skew,
        put_call_oi_ratio=pcr,
        oi_weighted_delta=None,
        oi_weighted_gamma=None,
        oi_weighted_theta=None,
        oi_weighted_vega=None,
    )


def test_bullish_when_signals_align():
    tech = make_tech(rsi14=25, macd_histogram=1.0)
    opts = make_opts(pcr=0.5, skew=-0.05)
    bias = evaluate_bias(tech, opts)
    assert bias.label == "Bullish"
    assert bias.score == 4


def test_bearish_when_signals_align():
    tech = make_tech(rsi14=80, macd_histogram=-1.0)
    opts = make_opts(pcr=1.5, skew=0.05)
    bias = evaluate_bias(tech, opts)
    assert bias.label == "Bearish"
    assert bias.score == -4


def test_neutral_with_no_data():
    tech = make_tech()
    bias = evaluate_bias(tech, None)
    assert bias.label == "Neutral"
    assert bias.score == 0
    assert bias.reasons == []


def test_neutral_with_mixed_signals():
    tech = make_tech(rsi14=50, macd_histogram=1.0)
    opts = make_opts(pcr=1.5, skew=None)
    bias = evaluate_bias(tech, opts)
    assert bias.label == "Neutral"


def test_bullish_at_score_one():
    tech = make_tech(rsi14=25, macd_histogram=None)
    bias = evaluate_bias(tech, None)
    assert bias.score == 1
    assert bias.label == "Bullish"


def test_bearish_at_score_negative_one():
    tech = make_tech(rsi14=80, macd_histogram=None)
    bias = evaluate_bias(tech, None)
    assert bias.score == -1
    assert bias.label == "Bearish"


def test_neutral_stays_neutral_at_score_zero():
    tech = make_tech(rsi14=None, macd_histogram=None)
    bias = evaluate_bias(tech, None)
    assert bias.score == 0
    assert bias.label == "Neutral"


def test_higher_threshold_needs_stronger_agreement():
    tech = make_tech(rsi14=25, macd_histogram=None)  # score == 1
    bias = evaluate_bias(tech, None, threshold=2)
    assert bias.score == 1
    assert bias.label == "Neutral"  # doesn't clear the higher bar


def test_higher_threshold_still_fires_on_full_agreement():
    tech = make_tech(rsi14=25, macd_histogram=1.0)
    opts = make_opts(pcr=0.5, skew=-0.05)  # score == 4
    bias = evaluate_bias(tech, opts, threshold=4)
    assert bias.label == "Bullish"
