from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

import httpx


class OKXClient:
    """Thin read-only wrapper around the OKX v5 REST API.

    Only ever issues GET requests against public/market-data endpoints.
    Signing is applied when API credentials are configured (OKX grants a
    higher rate-limit tier to authenticated requests) but no order-placement
    or trading endpoint is implemented anywhere in this client.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        api_secret: str = "",
        api_passphrase: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self._client = client or httpx.Client(timeout=15.0)

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def _sign_headers(self, method: str, request_path: str) -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + (
            f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
        )
        prehash = f"{timestamp}{method.upper()}{request_path}"
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
        }

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        query = httpx.QueryParams(params)
        request_path = path + (f"?{query}" if query else "")

        headers = {}
        if self.authenticated:
            headers = self._sign_headers("GET", request_path)

        resp = self._client.get(f"{self.base_url}{path}", params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") not in ("0", 0):
            raise OKXAPIError(payload.get("code"), payload.get("msg"))
        return payload.get("data", [])

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

    def close(self) -> None:
        self._client.close()


class OKXAPIError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(f"OKX API error {code}: {msg}")
        self.code = code
        self.msg = msg
