from __future__ import annotations

import httpx


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, client: httpx.Client | None = None) -> None:
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self._client = client or httpx.Client(timeout=10.0)

    def send(self, text: str) -> None:
        resp = self._client.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        resp.raise_for_status()

    def close(self) -> None:
        self._client.close()
