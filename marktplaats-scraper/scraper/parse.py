"""Turn a raw fetch.FetchResult (JSON from /lrp/api/search, or HTML with an
embedded __NEXT_DATA__ blob) into a list of scraper.schema.Listing.

Marktplaats' internal JSON shape is undocumented and can drift. Every field
lookup below tries a handful of plausible key paths and logs at DEBUG which
one matched (or that none did), instead of hard-crashing on a KeyError. If a
real run shows a field consistently coming back empty, capture a raw response
with `main.py --dump-raw` and adjust CANDIDATE_PATHS accordingly.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Optional

from bs4 import BeautifulSoup

from scraper.schema import Listing, SellerType

logger = logging.getLogger("scraper.parse")

BASE_URL = "https://www.marktplaats.nl"


def _dig(obj: Any, *paths: str) -> Optional[Any]:
    """Try several dotted key paths (e.g. "priceInfo.priceCents") against a
    dict, return the first non-None hit."""
    for path in paths:
        cur = obj
        ok = True
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _price_from_cents(cents: Optional[int]) -> Optional[float]:
    if cents is None:
        return None
    try:
        return round(int(cents) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def _guess_seller_type(item: dict) -> SellerType:
    seller = _dig(item, "sellerInformation", "seller") or {}
    if isinstance(seller, dict):
        if seller.get("isVerified") or seller.get("companyName") or seller.get("sellerWebsiteUrl"):
            return SellerType.ZAKELIJK
        if "sellerType" in seller:
            raw = str(seller["sellerType"]).lower()
            if "bus" in raw or "zakel" in raw:
                return SellerType.ZAKELIJK
            if "priv" in raw or "particul" in raw:
                return SellerType.PARTICULIER
    attrs = item.get("attributes") or item.get("extendedAttributes") or []
    for attr in attrs if isinstance(attrs, list) else []:
        key = str(attr.get("key", "")).lower()
        val = str(attr.get("value", "")).lower()
        if "seller" in key or "offeredby" in key or "aangebodendoor" in key:
            if "particul" in val or "priv" in val:
                return SellerType.PARTICULIER
            if "bedrijf" in val or "zakel" in val or "bus" in val:
                return SellerType.ZAKELIJK
    return SellerType.UNKNOWN


def _extract_condition(item: dict) -> Optional[str]:
    attrs = item.get("attributes") or item.get("extendedAttributes") or []
    for attr in attrs if isinstance(attrs, list) else []:
        key = str(attr.get("key", "")).lower()
        if "condition" in key or "staat" in key:
            return attr.get("value")
    return None


def _extract_images(item: dict) -> list[str]:
    pics = _dig(item, "pictures", "images", "imageUrls") or []
    urls: list[str] = []
    for pic in pics if isinstance(pics, list) else []:
        if isinstance(pic, str):
            urls.append(pic)
        elif isinstance(pic, dict):
            url = pic.get("largeUrl") or pic.get("mediumUrl") or pic.get("url") or pic.get("extraSmallUrl")
            if url:
                urls.append(url)
    return urls


def _item_to_listing(item: dict) -> Optional[Listing]:
    title = _dig(item, "title")
    url = _dig(item, "vipUrl", "url", "itemUrl")
    if not title or not url:
        logger.debug("Skipping item missing title/url: keys=%s", list(item.keys()))
        return None
    if not url.startswith("http"):
        url = BASE_URL + url

    price_cents = _dig(item, "priceInfo.priceCents", "price.cents", "priceCents")
    price_type = _dig(item, "priceInfo.priceType", "price.type", "priceType")

    return Listing(
        listing_id=str(_dig(item, "itemId", "id") or "") or None,
        title=title,
        price=_price_from_cents(price_cents),
        price_type=price_type,
        category=_dig(item, "categoryName", "category.name", "verticals"),
        condition=_extract_condition(item),
        location=_dig(item, "location.cityName", "location.city", "sellerInformation.location.cityName"),
        seller_type=_guess_seller_type(item),
        posted_date=_dig(item, "date", "sortTimestamp", "creationDate") or None,
        url=url,
        images=_extract_images(item),
        description_raw=_dig(item, "description"),
    )


def parse_api_response(raw_json: str) -> list[Listing]:
    """Parse a /lrp/api/search JSON response body."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.error("Failed to decode API response as JSON: %s", exc)
        return []

    items = _dig(data, "listings", "searchResult.listings", "itemsList") or []
    if not isinstance(items, list):
        logger.warning("API response 'listings' was not a list (shape drift?), got %s", type(items))
        return []

    listings: list[Listing] = []
    for item in items:
        try:
            listing = _item_to_listing(item)
        except Exception as exc:  # defensive: never let one bad item kill the run
            logger.warning("Failed to parse one API item: %s", exc)
            continue
        if listing:
            listings.append(listing)
    logger.info("Parsed %d/%d listings from API response", len(listings), len(items))
    return listings


_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


def _find_next_data(html: str) -> Optional[dict]:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return None
        raw = tag.string
    else:
        raw = match.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to decode __NEXT_DATA__ JSON: %s", exc)
        return None


def parse_search_html(html: str) -> list[Listing]:
    """Fallback parser: extract the Next.js __NEXT_DATA__ hydration payload
    embedded in the search results page HTML and read listings from it."""
    data = _find_next_data(html)
    if data is None:
        logger.error("No __NEXT_DATA__ blob found in HTML -- page shape may have changed")
        return []

    props = _dig(data, "props.pageProps")
    if not isinstance(props, dict):
        logger.warning("__NEXT_DATA__ had no props.pageProps -- shape drift?")
        return []

    items = (
        _dig(props, "searchRequestAndResponse.listings")
        or _dig(props, "searchResult.listings")
        or _dig(props, "listings")
        or []
    )
    if not isinstance(items, list):
        logger.warning("__NEXT_DATA__ listings was not a list (shape drift?)")
        return []

    listings: list[Listing] = []
    for item in items:
        try:
            listing = _item_to_listing(item)
        except Exception as exc:
            logger.warning("Failed to parse one __NEXT_DATA__ item: %s", exc)
            continue
        if listing:
            listings.append(listing)
    logger.info("Parsed %d/%d listings from __NEXT_DATA__ HTML fallback", len(listings), len(items))
    return listings
