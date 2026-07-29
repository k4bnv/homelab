from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx


class OKXClient:
    """Wrapper around the OKX v5 REST API.

    Market/public-data calls are always read-only GETs. Order placement
    (`place_market_order`) is only ever used against a demo-trading account
    when `demo=True` is set - every request then carries the
    `x-simulated-trading: 1` header, which routes the order to OKX's paper
    trading engine instead of the live market, regardless of which API key
    is configured.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        api_secret: str = "",
        api_passphrase: str = "",
        demo: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.demo = demo
        self._client = client or httpx.Client(timeout=15.0)

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def _sign_headers(self, method: str, request_path: str, body: str = "") -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + (
            f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
        )
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
        }

    def _extra_headers(self) -> dict:
        return {"x-simulated-trading": "1"} if self.demo else {}

    def _check_response(self, payload: dict) -> list[dict]:
        if payload.get("code") not in ("0", 0):
            raise OKXAPIError(payload.get("code"), payload.get("msg"))
        return payload.get("data", [])

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        query = httpx.QueryParams(params)
        request_path = path + (f"?{query}" if query else "")

        headers = self._extra_headers()
        if self.authenticated:
            headers.update(self._sign_headers("GET", request_path))

        resp = self._client.get(f"{self.base_url}{path}", params=params, headers=headers)
        resp.raise_for_status()
        return self._check_response(resp.json())

    def _post(self, path: str, body: dict) -> list[dict]:
        body_json = json.dumps(body)
        headers = {"Content-Type": "application/json", **self._extra_headers()}
        if self.authenticated:
            headers.update(self._sign_headers("POST", path, body_json))

        resp = self._client.post(f"{self.base_url}{path}", content=body_json, headers=headers)
        resp.raise_for_status()
        return self._check_response(resp.json())

    def get_candles(self, inst_id: str, bar: str = "15m", limit: int = 150) -> list[list[str]]:
        """Returns candles oldest -> newest: [ts, o, h, l, c, vol, ...]."""
        data = self._get(
            "/api/v5/market/candles",
            {"instId": inst_id, "bar": bar, "limit": min(limit, 300)},
        )
        return list(reversed(data))

    def get_index_ticker(self, inst_id: str) -> dict | None:
        data = self._get("/api/v5/market/index-tickers", {"instId": inst_id})
        return data[0] if data else None

    def get_opt_summary(self, uly: str, exp_time: str | None = None) -> list[dict]:
        return self._get("/api/v5/public/opt-summary", {"uly": uly, "expTime": exp_time})

    def get_open_interest(self, uly: str, inst_type: str = "OPTION") -> list[dict]:
        return self._get("/api/v5/public/open-interest", {"instType": inst_type, "uly": uly})

    def get_instruments(self, uly: str, inst_type: str = "OPTION") -> list[dict]:
        return self._get("/api/v5/public/instruments", {"instType": inst_type, "uly": uly})

    def get_ticker(self, inst_id: str) -> dict | None:
        data = self._get("/api/v5/market/ticker", {"instId": inst_id})
        return data[0] if data else None

    def get_mark_price(self, inst_id: str, inst_type: str = "OPTION") -> dict | None:
        """OKX's model/theoretical price - populated even when the order book
        has no resting bid/ask, unlike get_ticker."""
        data = self._get("/api/v5/public/mark-price", {"instType": inst_type, "instId": inst_id})
        return data[0] if data else None

    def place_order(
        self,
        inst_id: str,
        side: str,
        sz: str,
        ord_type: str = "market",
        td_mode: str = "cash",
        px: str | None = None,
        outcome: str | None = None,
        speed_bump: str | None = None,
    ) -> dict:
        """Places an order. `side` is 'buy' or 'sell'.

        `px` is required when `ord_type` is 'limit'/'post_only'. `outcome`
        ("yes"/"no") and `speed_bump` ("1") are only used for EVENTS (event
        contract) orders - omitted entirely for other instrument types.

        Returns the order ack (contains ordId, sCode, sMsg) - sCode == "0"
        means OKX accepted the order, it does not by itself mean filled.
        """
        body = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
        }
        if px is not None:
            body["px"] = px
        if outcome is not None:
            body["outcome"] = outcome
        if speed_bump is not None:
            body["speedBump"] = speed_bump
        data = self._post("/api/v5/trade/order", body)
        return data[0] if data else {}

    def cancel_order(self, inst_id: str, ord_id: str) -> dict:
        data = self._post("/api/v5/trade/cancel-order", {"instId": inst_id, "ordId": ord_id})
        return data[0] if data else {}

    def get_order(self, inst_id: str, ord_id: str) -> dict | None:
        data = self._get("/api/v5/trade/order", {"instId": inst_id, "ordId": ord_id})
        return data[0] if data else None

    def get_balance(self, ccy: str | None = None) -> dict | None:
        """Account balance/equity - reflects the demo balance when demo=True
        and a demo API key is configured."""
        data = self._get("/api/v5/account/balance", {"ccy": ccy} if ccy else None)
        return data[0] if data else None

    def get_event_series(self, series_id: str | None = None) -> list[dict]:
        """Lists Event Contract series, e.g. seriesId='BTC-UPDOWN-15MIN'.

        Despite the "/public/" path, OKX requires this to be a signed
        request (same as private endpoints).
        """
        return self._get("/api/v5/public/event-contract/series", {"seriesId": series_id})

    def get_event_markets(
        self,
        series_id: str,
        event_id: str | None = None,
        inst_id: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        """Lists tradeable Event Contract instruments within a series."""
        return self._get(
            "/api/v5/public/event-contract/markets",
            {"seriesId": series_id, "eventId": event_id, "instId": inst_id, "state": state},
        )

    def get_fills(
        self, inst_type: str, inst_id: str | None = None, ord_id: str | None = None
    ) -> list[dict]:
        return self._get(
            "/api/v5/trade/fills",
            {"instType": inst_type, "instId": inst_id, "ordId": ord_id},
        )

    def close(self) -> None:
        self._client.close()


class OKXAPIError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(f"OKX API error {code}: {msg}")
        self.code = code
        self.msg = msg
