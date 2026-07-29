from app import options_analysis


def make_raw(inst_id, delta_bs, gamma_bs, theta_bs, vega_bs, mark_vol):
    return {
        "instId": inst_id,
        "deltaBS": str(delta_bs),
        "gammaBS": str(gamma_bs),
        "thetaBS": str(theta_bs),
        "vegaBS": str(vega_bs),
        "markVol": str(mark_vol),
    }


RAW_SUMMARY = [
    make_raw("BTC-USD-250926-58000-C", 0.30, 0.0002, -12.0, 40.0, 0.52),
    make_raw("BTC-USD-250926-58000-P", -0.25, 0.0002, -11.0, 39.0, 0.55),
    make_raw("BTC-USD-250926-60000-C", 0.50, 0.00025, -13.0, 42.0, 0.50),
    make_raw("BTC-USD-250926-60000-P", -0.50, 0.00025, -13.0, 42.0, 0.51),
    make_raw("BTC-USD-251003-60000-C", 0.48, 0.0002, -10.0, 45.0, 0.49),
    make_raw("BTC-USD-251003-60000-P", -0.48, 0.0002, -10.0, 45.0, 0.50),
]

OI_RAW = [
    {"instId": "BTC-USD-250926-58000-C", "oi": "100"},
    {"instId": "BTC-USD-250926-58000-P", "oi": "50"},
    {"instId": "BTC-USD-250926-60000-C", "oi": "200"},
    {"instId": "BTC-USD-250926-60000-P", "oi": "300"},
    {"instId": "BTC-USD-251003-60000-C", "oi": "10"},
    {"instId": "BTC-USD-251003-60000-P", "oi": "10"},
]


def test_parse_opt_summary_extracts_strike_and_type():
    snapshots = options_analysis.parse_opt_summary("BTC-USD", RAW_SUMMARY)
    assert len(snapshots) == 6
    first = next(s for s in snapshots if s.inst_id == "BTC-USD-250926-58000-C")
    assert first.strike == 58000
    assert first.opt_type == "C"
    assert first.expiry == "250926"
    assert first.delta_bs == 0.30


def test_parse_opt_summary_skips_malformed_inst_id():
    bad = [make_raw("garbage", 0, 0, 0, 0, 0)]
    assert options_analysis.parse_opt_summary("BTC-USD", bad) == []


def test_nearest_expiry_picks_soonest():
    snapshots = options_analysis.parse_opt_summary("BTC-USD", RAW_SUMMARY)
    assert options_analysis.nearest_expiry(snapshots) == "250926"


def test_attach_open_interest_maps_by_inst_id():
    snapshots = options_analysis.parse_opt_summary("BTC-USD", RAW_SUMMARY)
    options_analysis.attach_open_interest(snapshots, OI_RAW)
    by_id = {s.inst_id: s.oi for s in snapshots}
    assert by_id["BTC-USD-250926-60000-C"] == 200
    assert by_id["BTC-USD-250926-60000-P"] == 300


def test_compute_metrics_uses_nearest_expiry_only():
    snapshots = options_analysis.parse_opt_summary("BTC-USD", RAW_SUMMARY)
    options_analysis.attach_open_interest(snapshots, OI_RAW)

    metrics = options_analysis.compute_metrics("BTC-USD", snapshots, spot=59500)

    assert metrics is not None
    assert metrics.expiry == "250926"
    assert metrics.contracts_considered == 4  # only 250926 expiry

    # spot 59500 is closer to strike 60000 than 58000
    assert metrics.atm_iv == (0.50 + 0.51) / 2

    # put OI (50+300) / call OI (100+200)
    assert metrics.put_call_oi_ratio == (350 / 300)


def test_compute_metrics_returns_none_without_data():
    assert options_analysis.compute_metrics("BTC-USD", [], spot=100) is None


def test_compute_metrics_handles_zero_open_interest():
    snapshots = options_analysis.parse_opt_summary(
        "BTC-USD",
        [make_raw("BTC-USD-250926-60000-C", 0.5, 0.0002, -10, 40, 0.5)],
    )
    metrics = options_analysis.compute_metrics("BTC-USD", snapshots, spot=60000)
    assert metrics.put_call_oi_ratio is None
    assert metrics.oi_weighted_delta is None
