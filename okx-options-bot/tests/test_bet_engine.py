import pytest

from app import bet_engine
from app.config import Settings
from app.db import BetsDB
from app.models import TechnicalSnapshot
from app.signal import Bias

INST_ID = "BTC-UPDOWN-15MIN-260729-1800-1815"


class FakeClient:
    def __init__(
        self,
        markets=None,
        order_acks=None,
        order_fills=None,
        fills=None,
        authenticated=True,
    ):
        self.markets = markets if markets is not None else []
        self.order_acks = order_acks or {}
        self.order_fills = order_fills or {}
        self.fills = fills if fills is not None else []
        self.authenticated = authenticated
        self.placed_orders = []
        self.cancelled_orders = []

    def get_event_markets(self, series_id, event_id=None, inst_id=None, state=None):
        return self.markets

    def place_order(
        self, inst_id, side, sz, ord_type="market", td_mode="cash", px=None, outcome=None, speed_bump=None
    ):
        self.placed_orders.append((inst_id, side, sz, ord_type, td_mode, px, outcome, speed_bump))
        key = (inst_id, side)
        return self.order_acks.get(key, {"sCode": "0", "ordId": f"ord-{inst_id}-{side}"})

    def cancel_order(self, inst_id, ord_id):
        self.cancelled_orders.append((inst_id, ord_id))
        return {"sCode": "0"}

    def get_order(self, inst_id, ord_id):
        return self.order_fills.get(ord_id)

    def get_fills(self, inst_type, inst_id=None, ord_id=None):
        return self.fills


def market(inst_id=INST_ID, exp_time=9999999999999, fix_time="1785317402015", floor_strike="64462.1"):
    return {
        "instId": inst_id,
        "expTime": str(exp_time),
        "fixTime": fix_time,
        "floorStrike": floor_strike,
        "seriesId": "BTC-UPDOWN-15MIN",
    }


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
    return Settings(stake_usd=5.0)


# ---------------------------------------------------------------------------
# select_current_event_market
# ---------------------------------------------------------------------------


def test_select_current_event_market_prefers_started_soonest_expiry():
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(
        markets=[
            market(inst_id="not-started", exp_time=now_ms + 20 * 60_000, fix_time=""),
            market(inst_id="started-soon", exp_time=now_ms + 5 * 60_000, fix_time="123"),
            market(inst_id="started-later", exp_time=now_ms + 10 * 60_000, fix_time="123"),
        ]
    )
    picked = bet_engine.select_current_event_market(client, "BTC")
    assert picked["instId"] == "started-soon"


def test_select_current_event_market_falls_back_when_none_started():
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(
        markets=[
            market(inst_id="a", exp_time=now_ms + 10 * 60_000, fix_time=""),
            market(inst_id="b", exp_time=now_ms + 5 * 60_000, fix_time=""),
        ]
    )
    picked = bet_engine.select_current_event_market(client, "BTC")
    assert picked["instId"] == "b"


def test_select_current_event_market_ignores_expired():
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(markets=[market(inst_id="expired", exp_time=now_ms - 1000)])
    assert bet_engine.select_current_event_market(client, "BTC") is None


def test_select_current_event_market_no_markets_returns_none():
    client = FakeClient(markets=[])
    assert bet_engine.select_current_event_market(client, "BTC") is None


# ---------------------------------------------------------------------------
# _open_new_bet
# ---------------------------------------------------------------------------


def test_open_new_bet_bullish_buys_yes(db, settings):
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(
        markets=[market(exp_time=now_ms + 5 * 60_000)],
        order_fills={
            f"ord-{INST_ID}-buy": {"state": "filled", "avgPx": "0.55", "accFillSz": "9.09"}
        },
    )
    bias = Bias(label="Bullish", score=2, reasons=["test"])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    open_bet = db.get_open_bet("BTC")
    assert open_bet is not None
    assert open_bet["direction"] == "UP"
    assert open_bet["inst_id"] == INST_ID
    assert open_bet["contracts"] == pytest.approx(9.09)
    assert open_bet["stake_usd"] == pytest.approx(0.55 * 9.09)
    assert (
        INST_ID, "buy", "5", "limit", "isolated", "0.99", "yes", "1"
    ) in client.placed_orders


def test_open_new_bet_bearish_buys_no(db, settings):
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(
        markets=[market(exp_time=now_ms + 5 * 60_000)],
        order_fills={
            f"ord-{INST_ID}-buy": {"state": "filled", "avgPx": "0.40", "accFillSz": "12.5"}
        },
    )
    bias = Bias(label="Bearish", score=-2, reasons=["test"])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    open_bet = db.get_open_bet("BTC")
    assert open_bet["direction"] == "DOWN"
    assert (
        INST_ID, "buy", "5", "limit", "isolated", "0.99", "no", "1"
    ) in client.placed_orders


def test_open_new_bet_neutral_does_nothing(db, settings):
    client = FakeClient()
    bias = Bias(label="Neutral", score=0, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert db.get_open_bet("BTC") is None
    assert client.placed_orders == []


def test_open_new_bet_skips_when_not_authenticated(db, settings):
    client = FakeClient(authenticated=False)
    bias = Bias(label="Bullish", score=2, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert db.get_open_bet("BTC") is None
    assert client.placed_orders == []


def test_open_new_bet_no_live_market_skips(db, settings):
    client = FakeClient(markets=[])
    bias = Bias(label="Bullish", score=2, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert db.get_open_bet("BTC") is None


def test_open_new_bet_order_rejected_skips(db, settings):
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(
        markets=[market(exp_time=now_ms + 5 * 60_000)],
        order_acks={(INST_ID, "buy"): {"sCode": "1", "sMsg": "insufficient balance"}},
    )
    bias = Bias(label="Bullish", score=2, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert db.get_open_bet("BTC") is None


def test_open_new_bet_never_fills_cancels_and_skips(db, settings, monkeypatch):
    monkeypatch.setattr(bet_engine, "FILL_POLL_ATTEMPTS", 2)
    monkeypatch.setattr(bet_engine, "FILL_POLL_DELAY_SECONDS", 0.01)
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(markets=[market(exp_time=now_ms + 5 * 60_000)], order_fills={})
    bias = Bias(label="Bullish", score=2, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert db.get_open_bet("BTC") is None
    assert client.cancelled_orders == [(INST_ID, f"ord-{INST_ID}-buy")]


def test_open_new_bet_stake_too_small_for_one_contract_skips(db):
    settings = Settings(stake_usd=0.5)  # < limit price 0.99, can't buy 1 contract
    now_ms = bet_engine.time.time() * 1000
    client = FakeClient(markets=[market(exp_time=now_ms + 5 * 60_000)])
    bias = Bias(label="Bullish", score=2, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert db.get_open_bet("BTC") is None
    assert client.placed_orders == []


def test_open_new_bet_uses_per_symbol_stake(db, settings):
    now_ms = bet_engine.time.time() * 1000
    settings = Settings(stake_usd=5.0, stake_usd_overrides="BTC:20")
    client = FakeClient(
        markets=[market(exp_time=now_ms + 5 * 60_000)],
        order_fills={
            f"ord-{INST_ID}-buy": {"state": "filled", "avgPx": "0.5", "accFillSz": "40"}
        },
    )
    bias = Bias(label="Bullish", score=2, reasons=[])

    bet_engine._open_new_bet(db, settings, client, "BTC", tech(), bias)

    assert (
        INST_ID, "buy", "20", "limit", "isolated", "0.99", "yes", "1"
    ) in client.placed_orders


# ---------------------------------------------------------------------------
# _close_open_bet
# ---------------------------------------------------------------------------


def _open(db, inst_id=INST_ID, symbol="BTC"):
    return db.open_bet(
        symbol=symbol,
        direction="UP",
        inst_id=inst_id,
        strike=64462.1,
        expiry="1785321000000",
        bias_score=2,
        opened_at="2026-01-01T00:00:00Z",
        entry_price=0.55,
        entry_spot=60000,
        contracts=9.09,
        stake_usd=5.0,
    )


def test_close_open_bet_no_position(db):
    client = FakeClient()
    result = bet_engine._close_open_bet(db, client, "BTC", 60000)
    assert result == "no open position"


def test_close_open_bet_skips_when_not_authenticated(db):
    _open(db)
    client = FakeClient(authenticated=False)
    bet_engine._close_open_bet(db, client, "BTC", 60000)
    assert db.get_open_bet("BTC") is not None


def test_close_open_bet_not_settled_yet_leaves_open(db):
    _open(db)
    client = FakeClient(fills=[])
    bet_engine._close_open_bet(db, client, "BTC", 60000)
    assert db.get_open_bet("BTC") is not None


def test_close_open_bet_win_settlement(db):
    _open(db)
    client = FakeClient(
        fills=[{"subType": "414", "fillPnl": "4.09", "ordId": "settle-1"}]
    )
    bet_engine._close_open_bet(db, client, "BTC", 61000)

    assert db.get_open_bet("BTC") is None
    closed = db.list_bets(limit=1)[0]
    assert closed["result"] == "WIN"
    assert closed["pnl_usd"] == pytest.approx(4.09)
    assert closed["exit_price"] == 1.0
    assert closed["exit_value_usd"] == pytest.approx(5.0 + 4.09)


def test_close_open_bet_loss_settlement(db):
    _open(db)
    client = FakeClient(
        fills=[{"subType": "415", "fillPnl": "-5.0", "ordId": "settle-2"}]
    )
    bet_engine._close_open_bet(db, client, "BTC", 59000)

    closed = db.list_bets(limit=1)[0]
    assert closed["result"] == "LOSS"
    assert closed["pnl_usd"] == pytest.approx(-5.0)
    assert closed["exit_price"] == 0.0


def test_close_open_bet_fetch_failure_leaves_open(db):
    _open(db)

    class BrokenClient(FakeClient):
        def get_fills(self, inst_type, inst_id=None, ord_id=None):
            raise RuntimeError("network error")

    client = BrokenClient(authenticated=True)
    bet_engine._close_open_bet(db, client, "BTC", 60000)
    assert db.get_open_bet("BTC") is not None
