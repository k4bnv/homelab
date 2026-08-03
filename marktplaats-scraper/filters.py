"""Keyword (laptop model) + price range filtering for parsed listings."""
from __future__ import annotations

from typing import Iterable, Optional

from scraper.schema import Listing


def matches_keywords(title: str, description: str, keywords: Iterable[str]) -> bool:
    keywords = list(keywords)
    if not keywords:
        return True
    haystack = f"{title} {description or ''}".lower()
    return any(kw.lower() in haystack for kw in keywords)


def in_price_range(price: Optional[float], min_price: Optional[float], max_price: Optional[float]) -> bool:
    if price is None:
        return False
    if min_price is not None and price < min_price:
        return False
    if max_price is not None and price > max_price:
        return False
    return True


def filter_listings(
    listings: Iterable[Listing],
    keywords: Iterable[str],
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[Listing]:
    keywords = list(keywords)
    out = []
    for listing in listings:
        if not matches_keywords(listing.title, listing.description_raw or "", keywords):
            continue
        if not in_price_range(listing.price, min_price, max_price):
            continue
        out.append(listing)
    return out
