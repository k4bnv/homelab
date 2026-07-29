import pytest

from app import bet_engine, options_analysis
from app.config import Settings
from app.db import BetsDB
from app.models import TechnicalSnapshot
from app.signal import Bias


def make_snapshot_raw(inst_id, delta_bs, mark_vol=0.5):
    return {
        "instId": inst_id,
        "deltaBS": str(delta_bs),
        "gammaBS": "0.0002",
        "thetaBS": "-10",
        "vegaBS": "40",
        "markVol": str(mark_vol),
    }


CALL_INST = "BTC-USD-991231-60000-C"
PUT_INST = "BTC-USD-991231-60000-P"

SNAPSHOTS = options_analysis.parse_opt_summary(
    "BTC-USD",
    [
        make_snapshot_raw(CALL_INST, 0.5),
        make_snapshot_raw(PUT_INST, -0.5),
    ],
)


class FakeClient:
    def __init__(self, tickers=None, instruments=None):
        self.tickers = tickers or {}
        self.instruments = instruments or {}

    def get_ticker(self, inst_id):
        return self.tickers.get(inst_id)

    def get_instruments(self, uly, inst_type="OPTION"):
        return list(self.instruments.get(uly, {}).values())


def usd_margined_instrument(inst_id):
    return {"instId": inst_id, "ctVal": "1", "ctValCcy": "USD"}


def tech(spot=60000.0):
    return TechnicalSnapshot(
        inst_id="BTC-USDT",
        spot=spot,
        rsi14=25.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        ema9=spot,
        ema21=spot,
    )


@pytest.fixture
def db(tmp_path):
    database = BetsDB(str(tmp_path / "bets.db"))
    yield database
    database.close()


@pytest.fixture
def settings():
    return Settings(stake_usd=5.0, starting_bankroll=1000.0)


def test_contract_usd_value_stable_margined():
    assert bet_engine.contract_usd_value(0.05, 1.0, "USD", "BTC", 60000) == pytest.approx(0.05)


def test_contract_usd_value_coin_margined():
    assert bet_engine.contract_usd_value(0.001, 1.0, "BTC", "BTC", 60000) == pytest.approx(60.0)


def test_contract_usd_value_unknown_ccy_raises():
    with pytest.raises(ValueError):
        bet_engine.contract_usd_value(1.0, 1.0, "ETH", "BTC", 60000)


def test_open_new_bet_bullish_opens_call(db, settings):
    client = FakeClient(
        tickers={CALL_INST: {"askPx": "0.05", "bidPx": "0.04"}},
        instruments={"BTC-USD": {CALL_INST: usd_margined_instrument(CALL_INST)}},
    )
    bias = Bias(label="Bullish", score=2, reasons=["test"])
    inst_by_id = {CALL_INST: usd_margined_instrument(CALL_INST)}

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias, SNAPSHOTS, inst_by_id)

    open_bet = db.get_open_bet("BTC")
    assert open_bet is not None
    assert open_bet["inst_id"] == CALL_INST
    assert open_bet["direction"] == "CALL"
    assert open_bet["contracts"] == pytest.approx(5.0 / 0.05)
    assert open_bet["stake_usd"] == 5.0


def test_open_new_bet_bearish_opens_put(db, settings):
    client = FakeClient()
    bias = Bias(label="Bearish", score=-2, reasons=["test"])
    inst_by_id = {PUT_INST: usd_margined_instrument(PUT_INST)}
    tickers = {PUT_INST: {"askPx": "0.06", "bidPx": "0.05"}}
    client.tickers = tickers

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias, SNAPSHOTS, inst_by_id)

    open_bet = db.get_open_bet("BTC")
    assert open_bet is not None
    assert open_bet["direction"] == "PUT"
    assert open_bet["inst_id"] == PUT_INST


def test_open_new_bet_neutral_does_nothing(db, settings):
    client = FakeClient()
    bias = Bias(label="Neutral", score=0, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias, SNAPSHOTS, {})

    assert db.get_open_bet("BTC") is None


def test_close_open_bet_computes_win(db, settings):
    db.open_bet(
        symbol="BTC",
        direction="CALL",
        inst_id=CALL_INST,
        strike=60000,
        expiry="991231",
        bias_score=2,
        opened_at="2026-01-01T00:00:00Z",
        entry_price=0.05,
        entry_spot=60000,
        contracts=100.0,  # stake $5 / $0.05
        stake_usd=5.0,
    )
    client = FakeClient(tickers={CALL_INST: {"bidPx": "0.06"}})
    inst_by_id = {CALL_INST: usd_margined_instrument(CALL_INST)}

    bet_engine._close_open_bet(db, client, "BTC", 61000, inst_by_id)

    assert db.get_open_bet("BTC") is None
    closed = db.list_bets(limit=1)[0]
    assert closed["status"] == "CLOSED"
    assert closed["result"] == "WIN"
    assert closed["pnl_usd"] == pytest.approx(1.0)  # 100 * 0.06 - 5


def test_close_open_bet_computes_loss(db, settings):
    db.open_bet(
        symbol="BTC",
        direction="CALL",
        inst_id=CALL_INST,
        strike=60000,
        expiry="991231",
        bias_score=2,
        opened_at="2026-01-01T00:00:00Z",
        entry_price=0.05,
        entry_spot=60000,
        contracts=100.0,
        stake_usd=5.0,
    )
    client = FakeClient(tickers={CALL_INST: {"bidPx": "0.03"}})
    inst_by_id = {CALL_INST: usd_margined_instrument(CALL_INST)}

    bet_engine._close_open_bet(db, client, "BTC", 59000, inst_by_id)

    closed = db.list_bets(limit=1)[0]
    assert closed["result"] == "LOSS"
    assert closed["pnl_usd"] == pytest.approx(-2.0)  # 100 * 0.03 - 5


def test_close_open_bet_no_ticker_leaves_open(db, settings):
    db.open_bet(
        symbol="BTC",
        direction="CALL",
        inst_id=CALL_INST,
        strike=60000,
        expiry="991231",
        bias_score=2,
        opened_at="2026-01-01T00:00:00Z",
        entry_price=0.05,
        entry_spot=60000,
        contracts=100.0,
        stake_usd=5.0,
    )
    client = FakeClient()  # no ticker data available

    bet_engine._close_open_bet(db, client, "BTC", 60000, {CALL_INST: usd_margined_instrument(CALL_INST)})

    assert db.get_open_bet("BTC") is not None
