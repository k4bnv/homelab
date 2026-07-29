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


@respx.mock
def test_get_mark_price_returns_first_item():
    respx.get(f"{BASE_URL}/api/v5/public/mark-price").mock(
        return_value=httpx.Response(
            200,
            json={"code": "0", "msg": "", "data": [{"instId": "BTC-USDT", "markPx": "0.05"}]},
        )
    )
    client = OKXClient(BASE_URL)
    mark = client.get_mark_price("BTC-USDT")
    assert mark == {"instId": "BTC-USDT", "markPx": "0.05"}


@respx.mock
def test_get_mark_price_returns_none_when_empty():
    respx.get(f"{BASE_URL}/api/v5/public/mark-price").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL)
    assert client.get_mark_price("BTC-USDT") is None


@respx.mock
def test_get_balance_with_ccy_filter():
    route = respx.get(f"{BASE_URL}/api/v5/account/balance").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "totalEq": "1000",
                        "details": [{"ccy": "USDT", "availBal": "1000", "eq": "1000"}],
                    }
                ],
            },
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    balance = client.get_balance(ccy="USDT")
    assert balance["details"][0]["ccy"] == "USDT"
    assert route.calls.last.request.url.params["ccy"] == "USDT"


@respx.mock
def test_get_balance_returns_none_when_empty():
    respx.get(f"{BASE_URL}/api/v5/account/balance").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    assert client.get_balance() is None


@respx.mock
def test_demo_client_sends_simulated_trading_header_on_get():
    route = respx.get(f"{BASE_URL}/api/v5/public/open-interest").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL, demo=True)
    client.get_open_interest("BTC-USD")
    assert route.calls.last.request.headers["x-simulated-trading"] == "1"


@respx.mock
def test_non_demo_client_has_no_simulated_trading_header():
    route = respx.get(f"{BASE_URL}/api/v5/public/open-interest").mock(
        return_value=httpx.Response(200, json={"code": "0", "msg": "", "data": []})
    )
    client = OKXClient(BASE_URL, demo=False)
    client.get_open_interest("BTC-USD")
    assert "x-simulated-trading" not in route.calls.last.request.headers


@respx.mock
def test_place_order_sends_signed_post_with_demo_header():
    route = respx.post(f"{BASE_URL}/api/v5/trade/order").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "",
                "data": [{"ordId": "12345", "sCode": "0", "sMsg": ""}],
            },
        )
    )
    client = OKXClient(
        BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase", demo=True
    )
    ack = client.place_order("BTC-USD-991231-60000-C", side="buy", sz="0.5")

    assert ack == {"ordId": "12345", "sCode": "0", "sMsg": ""}
    request = route.calls.last.request
    assert request.headers["x-simulated-trading"] == "1"
    assert request.headers["OK-ACCESS-KEY"] == "key"
    assert request.headers["Content-Type"] == "application/json"
    import json as _json

    body = _json.loads(request.content)
    assert body == {
        "instId": "BTC-USD-991231-60000-C",
        "tdMode": "cash",
        "side": "buy",
        "ordType": "market",
        "sz": "0.5",
    }


@respx.mock
def test_place_order_raises_on_top_level_error():
    respx.post(f"{BASE_URL}/api/v5/trade/order").mock(
        return_value=httpx.Response(200, json={"code": "50001", "msg": "auth failed", "data": []})
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    with pytest.raises(OKXAPIError):
        client.place_order("BTC-USD-991231-60000-C", side="buy", sz="0.5")


@respx.mock
def test_get_order_returns_first_item():
    respx.get(f"{BASE_URL}/api/v5/trade/order").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "",
                "data": [{"ordId": "12345", "state": "filled", "avgPx": "0.05"}],
            },
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    order = client.get_order("BTC-USD-991231-60000-C", "12345")
    assert order["state"] == "filled"
    assert order["avgPx"] == "0.05"


@respx.mock
def test_place_order_includes_outcome_and_speed_bump_for_events():
    route = respx.post(f"{BASE_URL}/api/v5/trade/order").mock(
        return_value=httpx.Response(
            200, json={"code": "0", "msg": "", "data": [{"ordId": "1", "sCode": "0"}]}
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    client.place_order(
        "BTC-UPDOWN-15MIN-260729-1800-1815",
        side="buy",
        sz="5",
        td_mode="isolated",
        outcome="yes",
        speed_bump="1",
    )
    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body == {
        "instId": "BTC-UPDOWN-15MIN-260729-1800-1815",
        "tdMode": "isolated",
        "side": "buy",
        "ordType": "market",
        "sz": "5",
        "outcome": "yes",
        "speedBump": "1",
    }


@respx.mock
def test_place_order_limit_includes_px():
    route = respx.post(f"{BASE_URL}/api/v5/trade/order").mock(
        return_value=httpx.Response(
            200, json={"code": "0", "msg": "", "data": [{"ordId": "1", "sCode": "0"}]}
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    client.place_order(
        "BTC-UPDOWN-15MIN-260729-1800-1815",
        side="buy",
        sz="5",
        ord_type="limit",
        td_mode="isolated",
        px="0.99",
        outcome="yes",
        speed_bump="1",
    )
    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body["ordType"] == "limit"
    assert body["px"] == "0.99"


@respx.mock
def test_cancel_order_sends_signed_post():
    route = respx.post(f"{BASE_URL}/api/v5/trade/cancel-order").mock(
        return_value=httpx.Response(
            200, json={"code": "0", "msg": "", "data": [{"ordId": "1", "sCode": "0"}]}
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    result = client.cancel_order("BTC-UPDOWN-15MIN-260729-1800-1815", "1")
    assert result == {"ordId": "1", "sCode": "0"}
    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body == {"instId": "BTC-UPDOWN-15MIN-260729-1800-1815", "ordId": "1"}


@respx.mock
def test_get_event_series_passes_series_id_filter():
    route = respx.get(f"{BASE_URL}/api/v5/public/event-contract/series").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "",
                "data": [{"seriesId": "BTC-UPDOWN-15MIN", "freq": "fifteen_min"}],
            },
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    series = client.get_event_series("BTC-UPDOWN-15MIN")
    assert series[0]["seriesId"] == "BTC-UPDOWN-15MIN"
    assert route.calls.last.request.url.params["seriesId"] == "BTC-UPDOWN-15MIN"


@respx.mock
def test_get_event_markets_returns_data():
    respx.get(f"{BASE_URL}/api/v5/public/event-contract/markets").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "",
                "data": [{"instId": "BTC-UPDOWN-15MIN-260729-1800-1815", "state": "live"}],
            },
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    markets = client.get_event_markets("BTC-UPDOWN-15MIN", state="live")
    assert markets[0]["instId"] == "BTC-UPDOWN-15MIN-260729-1800-1815"


@respx.mock
def test_get_fills_passes_inst_type_and_inst_id():
    route = respx.get(f"{BASE_URL}/api/v5/trade/fills").mock(
        return_value=httpx.Response(
            200,
            json={"code": "0", "msg": "", "data": [{"subType": "414", "fillPnl": "1.23"}]},
        )
    )
    client = OKXClient(BASE_URL, api_key="key", api_secret="secret", api_passphrase="phrase")
    fills = client.get_fills("EVENTS", inst_id="BTC-UPDOWN-15MIN-260729-1800-1815")
    assert fills[0]["fillPnl"] == "1.23"
    params = route.calls.last.request.url.params
    assert params["instType"] == "EVENTS"
    assert params["instId"] == "BTC-UPDOWN-15MIN-260729-1800-1815"
