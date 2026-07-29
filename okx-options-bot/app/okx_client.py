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

    def place_market_order(self, inst_id: str, side: str, sz: str, td_mode: str = "cash") -> dict:
        """Places a market order. `side` is 'buy' or 'sell'.

        Returns the order ack (contains ordId, sCode, sMsg) - sCode == "0"
        means OKX accepted the order, it does not by itself mean filled.
        """
        data = self._post(
            "/api/v5/trade/order",
            {
                "instId": inst_id,
                "tdMode": td_mode,
                "side": side,
                "ordType": "market",
                "sz": sz,
            },
        )
        return data[0] if data else {}

    def get_order(self, inst_id: str, ord_id: str) -> dict | None:
        data = self._get("/api/v5/trade/order", {"instId": inst_id, "ordId": ord_id})
        return data[0] if data else None

    def close(self) -> None:
        self._client.close()


class OKXAPIError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(f"OKX API error {code}: {msg}")
        self.code = code
        self.msg = msg
