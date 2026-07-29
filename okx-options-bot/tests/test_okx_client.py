import httpx
import pytest
import respx

from app.okx_client import OKXAPIError, OKXClient

BASE_URL = "https://www.okx.com"


@respx.mock
def test_get_candles_returns_oldest_to_newest():
    route = respx.get(f"{BASE_URL}/api/v5/market/candles").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "",
                "data": [
                    ["3000", "o3", "h3", "l3", "c3", "v3"],
                    ["2000", "o2", "h2", "l2", "c2", "v2"],
                    ["1000", "o1", "h1", "l1", "c1", "v1"],
                ],
            },
        )
    )
    client = OKXClient(BASE_URL)
    candles = client.get_candles("BTC-USDT", bar="15m", limit=3)
    assert route.called
    assert [c[0] for c in candles] == ["1000", "2000", "3000"]


@respx.mock
def test_get_opt_summary_raises_on_error_code():
    respx.get(f"{BASE_URL}/api/v5/public/opt-summary").mock(
        return_value=httpx.Response(200, json={"code": "50001", "msg": "boom", "data": []})
    )
    client = OKXClient(BASE_URL)
    with pytest.raises(OKXAPIError):
        client.get_opt_summary("BTC-USD")


@respx.mock
def test_unauthenticated_requests_have_no_ok_access_headers():
    route = respx.get(f"{BASE_URL}/api/v5/public/open-interest").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL)
    client.get_open_interest("BTC-USD")
    sent_headers = route.calls.last.request.headers
    assert "OK-ACCESS-KEY" not in sent_headers


@respx.mock
def test_authenticated_requests_include_signed_headers():
    route = respx.get(f"{BASE_URL}/api/v5/public/open-interest").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    assert client.authenticated
    client.get_open_interest("BTC-USD")
    sent_headers = route.calls.last.request.headers
    assert sent_headers["OK-ACCESS-KEY"] == "key"
    assert sent_headers["OK-ACCESS-PASSPHRASE"] == "phrase"
    assert sent_headers["OK-ACCESS-SIGN"]
    assert sent_headers["OK-ACCESS-TIMESTAMP"].endswith("Z")


@respx.mock
def test_get_instruments_returns_data():
    respx.get(f"{BASE_URL}/api/v5/public/instruments").mock(
        return_value=httpx.Response(
            200,
            json={"code": "0", "msg": "", "data": [{"instId": "BTC-USD-991231-60000-C"}]},
        )
    )
    client = OKXClient(BASE_URL)
    instruments = client.get_instruments("BTC-USD")
    assert instruments == [{"instId": "BTC-USD-991231-60000-C"}]


@respx.mock
def test_get_ticker_returns_first_item():
    respx.get(f"{BASE_URL}/api/v5/market/ticker").mock(
        return_value=httpx.Response(
            200,
            json={"code": "0", "msg": "", "data": [{"instId": "BTC-USDT", "last": "60000"}]},
        )
    )
    client = OKXClient(BASE_URL)
    ticker = client.get_ticker("BTC-USDT")
    assert ticker == {"instId": "BTC-USDT", "last": "60000"}


@respx.mock
def test_get_ticker_returns_none_when_empty():
    respx.get(f"{BASE_URL}/api/v5/market/ticker").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL)
    assert client.get_ticker("BTC-USDT") is None
