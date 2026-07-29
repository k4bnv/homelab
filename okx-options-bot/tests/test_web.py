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


def test_index_sends_no_cache_header(client):
    resp = client.get("/")
    assert "no-cache" in resp.headers["cache-control"]


def test_static_assets_send_no_cache_header(client):
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "no-cache" in resp.headers["cache-control"]


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

    def get_balance(self, ccy=None):
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


def test_okx_balance_returns_usdt_only(tmp_path):
    db = BetsDB(str(tmp_path / "bets4.db"))
    settings = Settings()
    fake_client = FakeOKXClient(
        authenticated=True,
        demo=True,
        balance={
            "totalEq": "1234.5",
            "details": [
                {"ccy": "USDT", "availBal": "1000.0", "eq": "1000.0"},
            ],
        },
    )
    app = create_app(db, settings, fake_client)
    with TestClient(app) as test_client:
        resp = test_client.get("/api/okx-balance")
        data = resp.json()
        assert data["available"] is True
        assert data["ccy"] == "USDT"
        assert data["avail_bal"] == 1000.0
        assert data["eq"] == 1000.0
        assert data["demo"] is True
    db.close()


def test_okx_balance_unavailable_when_no_usdt(tmp_path):
    db = BetsDB(str(tmp_path / "bets5.db"))
    settings = Settings()
    fake_client = FakeOKXClient(
        authenticated=True,
        demo=True,
        balance={"totalEq": "10", "details": [{"ccy": "BTC", "availBal": "0.001", "eq": "60"}]},
    )
    app = create_app(db, settings, fake_client)
    with TestClient(app) as test_client:
        resp = test_client.get("/api/okx-balance")
        data = resp.json()
        assert data["available"] is False
    db.close()


def test_settings_endpoint_excludes_secrets(tmp_path):
    db = BetsDB(str(tmp_path / "bets6.db"))
    settings = Settings(
        okx_api_key="secret-key",
        okx_api_secret="secret-secret",
        okx_api_passphrase="secret-pass",
        bias_threshold=2,
        stake_usd=7.0,
        stake_usd_overrides="BTC:10",
        symbols="BTC,ETH",
    )
    fake_client = FakeOKXClient(authenticated=True)
    app = create_app(db, settings, fake_client)
    with TestClient(app) as test_client:
        resp = test_client.get("/api/settings")
        data = resp.json()
        assert data["bias_threshold"] == 2
        assert data["stake_usd"] == 7.0
        assert data["stake_overrides"] == {"BTC": 10.0}
        assert data["symbols"] == ["BTC", "ETH"]
        assert data["okx_authenticated"] is True
        blob = str(data)
        assert "secret-key" not in blob
        assert "secret-secret" not in blob
        assert "secret-pass" not in blob
    db.close()
