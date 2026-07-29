import pytest

from app.db import BetsDB


@pytest.fixture
def db(tmp_path):
    database = BetsDB(str(tmp_path / "nested" / "bets.db"))
    yield database
    database.close()


def _open(db, symbol="BTC", inst_id="BTC-USD-991231-60000-C"):
    return db.open_bet(
        symbol=symbol,
        direction="CALL",
        inst_id=inst_id,
        strike=60000,
        expiry="991231",
        bias_score=2,
        opened_at="2026-01-01T00:00:00Z",
        entry_price=0.05,
        entry_spot=60000,
        contracts=100.0,
        stake_usd=5.0,
    )


def test_open_bet_creates_db_file_and_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "bets.db"
    db = BetsDB(str(path))
    assert path.exists()
    db.close()


def test_get_open_bet_returns_none_when_no_bets(db):
    assert db.get_open_bet("BTC") is None


def test_open_bet_then_get_open_bet(db):
    bet_id = _open(db)
    open_bet = db.get_open_bet("BTC")
    assert open_bet["id"] == bet_id
    assert open_bet["status"] == "OPEN"


def test_get_open_bet_is_symbol_scoped(db):
    _open(db, symbol="BTC")
    assert db.get_open_bet("ETH") is None


def test_close_bet_updates_status_and_result(db):
    bet_id = _open(db)
    db.close_bet(
        bet_id,
        closed_at="2026-01-01T00:15:00Z",
        exit_price=0.06,
        exit_spot=61000,
        exit_value_usd=6.0,
        pnl_usd=1.0,
        result="WIN",
    )
    assert db.get_open_bet("BTC") is None
    closed = db.list_bets(limit=1)[0]
    assert closed["status"] == "CLOSED"
    assert closed["result"] == "WIN"
    assert closed["pnl_usd"] == 1.0


def test_list_bets_orders_newest_first(db):
    _open(db, inst_id="BTC-USD-991231-60000-C")
    _open(db, inst_id="BTC-USD-991231-61000-C")
    bets = db.list_bets(limit=10)
    assert [b["inst_id"] for b in bets] == [
        "BTC-USD-991231-61000-C",
        "BTC-USD-991231-60000-C",
    ]


def test_list_bets_filters_by_symbol(db):
    _open(db, symbol="BTC")
    _open(db, symbol="ETH", inst_id="ETH-USD-991231-3000-C")
    bets = db.list_bets(limit=10, symbol="ETH")
    assert len(bets) == 1
    assert bets[0]["symbol"] == "ETH"


def test_closed_bets_chronological_only_returns_closed(db):
    open_id = _open(db, inst_id="a")
    closed_id = _open(db, inst_id="b")
    db.close_bet(
        closed_id,
        closed_at="t",
        exit_price=0.06,
        exit_spot=61000,
        exit_value_usd=6.0,
        pnl_usd=1.0,
        result="WIN",
    )
    rows = db.closed_bets_chronological()
    assert len(rows) == 1
    assert rows[0]["id"] == closed_id
    assert open_id != closed_id


def test_list_activity_empty(db):
    assert db.list_activity() == []


def test_log_activity_then_list(db):
    db.log_activity(
        ts="2026-01-01T00:00:00Z",
        symbol="BTC",
        bias_label="Bullish",
        bias_score=2,
        message="opened CALL ...",
    )
    rows = db.list_activity()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC"
    assert rows[0]["bias_label"] == "Bullish"
    assert rows[0]["message"] == "opened CALL ..."


def test_list_activity_orders_newest_first_and_respects_limit(db):
    for i in range(5):
        db.log_activity(
            ts=f"t{i}", symbol="BTC", bias_label="Neutral", bias_score=0, message=f"msg{i}"
        )
    rows = db.list_activity(limit=2)
    assert [r["message"] for r in rows] == ["msg4", "msg3"]
