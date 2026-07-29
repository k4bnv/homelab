import threading
from unittest.mock import patch

import pytest

from app import main
from app.config import Settings
from app.db import BetsDB


@pytest.fixture
def db(tmp_path):
    database = BetsDB(str(tmp_path / "bets.db"))
    yield database
    database.close()


class ExplodingClient:
    authenticated = False
    demo = True


def test_run_scheduler_logs_activity_when_run_symbol_raises(db):
    settings = Settings(symbols="BTC", poll_interval_seconds=60)
    stop_event = threading.Event()

    call_count = {"n": 0}

    def fake_run_symbol(db_arg, client_arg, settings_arg, symbol):
        call_count["n"] += 1
        stop_event.set()  # stop after the first (failing) cycle
        raise RuntimeError("boom")

    with (
        patch("app.main.seconds_until_next_run", return_value=0),
        patch("app.bet_engine.run_symbol", side_effect=fake_run_symbol),
    ):
        main.run_scheduler(db, ExplodingClient(), settings, stop_event)

    assert call_count["n"] == 1
    rows = db.list_activity()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC"
    assert rows[0]["bias_label"] == "Error"
    assert "boom" in rows[0]["message"]
