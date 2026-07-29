import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import BetsDB
from app.web import create_app


@pytest.fixture
def client(tmp_path):
    db = BetsDB(str(tmp_path / "bets.db"))
    settings = Settings(starting_bankroll=1000.0, stake_usd=5.0)

    bet_id = db.open_bet(
        symbol="BTC",
        direction="CALL",
        inst_id="BTC-USD-991231-60000-C",
        strike=60000,
        expiry="991231",
        bias_score=2,
        opened_at="2026-01-01T00:00:00Z",
        entry_price=0.05,
        entry_spot=60000,
        contracts=100.0,
        stake_usd=5.0,
    )
    db.close_bet(
        bet_id,
        closed_at="2026-01-01T00:15:00Z",
        exit_price=0.06,
        exit_spot=61000,
        exit_value_usd=6.0,
        pnl_usd=1.0,
        result="WIN",
    )

    app = create_app(db, settings)
    with TestClient(app) as test_client:
        yield test_client
    db.close()


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "OKX Options Bot" in resp.text


def test_summary_reflects_closed_bet(client):
    resp = client.get("/api/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_bets"] == 1
    assert data["wins"] == 1
    assert data["losses"] == 0
    assert data["balance"] == 1001.0
    assert data["by_symbol"]["BTC"]["wins"] == 1


def test_bets_endpoint_returns_list(client):
    resp = client.get("/api/bets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["inst_id"] == "BTC-USD-991231-60000-C"


def test_bets_endpoint_filters_by_symbol(client):
    resp = client.get("/api/bets", params={"symbol": "ETH"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_equity_curve_endpoint(client):
    resp = client.get("/api/equity-curve")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["balance"] == 1000.0
    assert data[-1]["balance"] == 1001.0


def test_activity_endpoint_empty(client):
    resp = client.get("/api/activity")
    assert resp.status_code == 200
    assert resp.json() == []


def test_activity_endpoint_returns_logged_entries(tmp_path):
    db = BetsDB(str(tmp_path / "bets2.db"))
    db.log_activity(
        ts="2026-01-01T00:00:00Z",
        symbol="BTC",
        bias_label="Bullish",
        bias_score=2,
        message="opened CALL",
    )
    settings = Settings()
    app = create_app(db, settings)
    with TestClient(app) as test_client:
        resp = test_client.get("/api/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["message"] == "opened CALL"
    db.close()


def test_okx_balance_unavailable_without_client(client):
    resp = client.get("/api/okx-balance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False


class FakeOKXClient:
    def __init__(self, authenticated=True, demo=True, balance=None):
        self.authenticated = authenticated
        self.demo = demo
        self._balance = balance

    def get_balance(self):
        return self._balance


def test_okx_balance_unavailable_when_not_authenticated(tmp_path):
    db = BetsDB(str(tmp_path / "bets3.db"))
    settings = Settings()
    fake_client = FakeOKXClient(authenticated=False)
    app = create_app(db, settings, fake_client)
    with TestClient(app) as test_client:
        resp = test_client.get("/api/okx-balance")
        assert resp.json()["available"] is False
    db.close()


def test_okx_balance_returns_equity_and_details(tmp_path):
    db = BetsDB(str(tmp_path / "bets4.db"))
    settings = Settings()
    fake_client = FakeOKXClient(
        authenticated=True,
        demo=True,
        balance={
            "totalEq": "1234.5",
            "details": [
                {"ccy": "USDT", "availBal": "1000.0", "eq": "1000.0"},
                {"ccy": "BTC", "availBal": "0", "eq": "0"},
            ],
        },
    )
    app = create_app(db, settings, fake_client)
    with TestClient(app) as test_client:
        resp = test_client.get("/api/okx-balance")
        data = resp.json()
        assert data["available"] is True
        assert data["total_eq_usd"] == 1234.5
        assert data["demo"] is True
        assert len(data["details"]) == 1  # zero-eq BTC filtered out
        assert data["details"][0]["ccy"] == "USDT"
    db.close()
