"""Telegram alert stub. Never raises -- a notify failure must not crash a scrape run."""
from __future__ import annotations

import logging
import os

import requests

from scraper.schema import Listing

logger = logging.getLogger("scraper.notify")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def format_price_alert(listing: Listing, threshold: float) -> str:
    return (
        f"\U0001F4BB <b>{listing.title}</b>\n"
        f"Цена: {listing.price} € (порог: {threshold} €)\n"
        f"Локация: {listing.location or '—'}\n"
        f"Состояние: {listing.condition or '—'}\n"
        f"{listing.url}"
    )


def send_telegram_message(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.info("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing) -- skipping alert")
        return False
    url = TELEGRAM_API_URL.format(token=token)
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram alert: %s", exc)
        return False


def notify_price_alert(listing: Listing, threshold: float) -> bool:
    return send_telegram_message(format_price_alert(listing, threshold))
