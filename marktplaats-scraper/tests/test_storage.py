import tempfile
from pathlib import Path

import pytest

from scraper.schema import Listing, SellerType
from storage import Storage


@pytest.fixture()
def storage():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "listings.db"
        s = Storage(db_path)
        yield s
        s.close()


def _listing(price=150.0, url="https://www.marktplaats.nl/v/x/y/m1-test"):
    return Listing(
        listing_id="m1",
        title="Test ThinkPad T480",
        price=price,
        url=url,
        seller_type=SellerType.PARTICULIER,
    )


def test_insert_new_listing(storage):
    result = storage.upsert_listing(_listing())
    assert result == {"status": "new", "price_changed": False, "old_price": None}
    row = storage.get_by_url("https://www.marktplaats.nl/v/x/y/m1-test")
    assert row["price"] == 150.0


def test_rerun_same_price_updates_not_duplicates(storage):
    storage.upsert_listing(_listing(price=150.0))
    result = storage.upsert_listing(_listing(price=150.0))
    assert result["status"] == "updated"
    assert result["price_changed"] is False
    cur = storage._conn.execute("SELECT COUNT(*) FROM listings")
    assert cur.fetchone()[0] == 1


def test_price_change_detected_and_not_duplicated(storage):
    storage.upsert_listing(_listing(price=150.0))
    result = storage.upsert_listing(_listing(price=120.0))
    assert result["status"] == "updated"
    assert result["price_changed"] is True
    assert result["old_price"] == 150.0
    cur = storage._conn.execute("SELECT COUNT(*) FROM listings")
    assert cur.fetchone()[0] == 1
    row = storage.get_by_url("https://www.marktplaats.nl/v/x/y/m1-test")
    assert row["price"] == 120.0
