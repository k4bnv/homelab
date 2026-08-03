"""SQLite storage for listings. Idempotent: re-running the scraper updates
price/last_seen on existing rows (matched by unique url) instead of duplicating."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scraper.enrich import LaptopSpecs
from scraper.schema import Listing

logger = logging.getLogger("scraper.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    listing_id TEXT,
    title TEXT NOT NULL,
    price REAL,
    price_type TEXT,
    category TEXT,
    condition TEXT,
    location TEXT,
    seller_type TEXT,
    posted_date TEXT,
    images TEXT,
    description_raw TEXT,
    enriched_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_price_change_at TEXT,
    notified_at TEXT
);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def upsert_listing(self, listing: Listing, enriched: Optional[LaptopSpecs] = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        images_json = json.dumps(listing.images)
        enriched_json = json.dumps(enriched.model_dump()) if enriched else None
        posted_date = listing.posted_date.isoformat() if listing.posted_date else None

        cur = self._conn.execute("SELECT id, price FROM listings WHERE url = ?", (listing.url,))
        row = cur.fetchone()

        if row is None:
            self._conn.execute(
                """INSERT INTO listings (
                    url, listing_id, title, price, price_type, category, condition, location,
                    seller_type, posted_date, images, description_raw, enriched_json,
                    first_seen_at, last_seen_at, last_price_change_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    listing.url, listing.listing_id, listing.title, listing.price, listing.price_type,
                    listing.category, listing.condition, listing.location, listing.seller_type.value,
                    posted_date, images_json, listing.description_raw, enriched_json, now, now, now,
                ),
            )
            self._conn.commit()
            logger.info("NEW listing stored: %r price=%s url=%s", listing.title, listing.price, listing.url)
            return {"status": "new", "price_changed": False, "old_price": None}

        listing_id, old_price = row
        price_changed = old_price != listing.price
        if price_changed:
            self._conn.execute(
                """UPDATE listings SET
                    price=?, last_seen_at=?, last_price_change_at=?, title=?, category=?,
                    condition=?, location=?, seller_type=?, images=?, description_raw=?,
                    enriched_json=COALESCE(?, enriched_json)
                   WHERE id=?""",
                (
                    listing.price, now, now, listing.title, listing.category, listing.condition,
                    listing.location, listing.seller_type.value, images_json, listing.description_raw,
                    enriched_json, listing_id,
                ),
            )
            logger.info("PRICE CHANGE %s: %s -> %s", listing.url, old_price, listing.price)
        else:
            self._conn.execute(
                """UPDATE listings SET last_seen_at=?, title=?, enriched_json=COALESCE(?, enriched_json)
                   WHERE id=?""",
                (now, listing.title, enriched_json, listing_id),
            )
        self._conn.commit()
        return {"status": "updated", "price_changed": price_changed, "old_price": old_price}

    def mark_notified(self, url: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE listings SET notified_at=? WHERE url=?", (now, url))
        self._conn.commit()

    def get_by_url(self, url: str) -> Optional[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute("SELECT * FROM listings WHERE url=?", (url,))
        return cur.fetchone()
