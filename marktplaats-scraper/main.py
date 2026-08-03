#!/usr/bin/env python3
"""CLI entrypoint for the Marktplaats laptop-flipping scraper.

Usage:
    python main.py --query "thinkpad t480" --max-price 200 --zipcode 1011AB --radius 25

Meant to be invoked once per cron tick (every 30-60 min), never in a loop.
See README.md "Как не словить бан" before changing the schedule.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import quote

import yaml
from dotenv import load_dotenv

from filters import filter_listings
from notify import notify_price_alert
from scraper.enrich import enrich_description
from scraper.fetch import (
    BASE_URL,
    SEARCH_API_PATH,
    SEARCH_HTML_PATH,
    BanDetected,
    Fetcher,
    RequestBudgetExceeded,
    RobotsDisallowed,
)
from scraper.parse import parse_api_response, parse_search_html
from scraper.schema import Listing
from storage import Storage

logger = logging.getLogger("scraper.main")


def setup_logging(log_path: Path, debug: bool = False) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def load_config(path: Path) -> dict:
    if not path.exists():
        logger.warning("Config file %s not found, using built-in defaults", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_search_url_and_params(query: str, zipcode: str | None, radius_km: float | None) -> tuple[str, dict]:
    url = BASE_URL + SEARCH_API_PATH
    params: dict = {"query": query}
    if zipcode:
        # NOTE: param names below (postcode / distanceMeters) are best-effort
        # guesses at Marktplaats' undocumented API and may need adjusting --
        # capture a real request in browser devtools and compare if location
        # filtering doesn't behave as expected.
        params["postcode"] = zipcode
        if radius_km:
            params["distanceMeters"] = int(radius_km * 1000)
    return url, params


def fetch_listings(fetcher: Fetcher, query: str, zipcode: str | None, radius_km: float | None) -> list[Listing]:
    api_url, api_params = build_search_url_and_params(query, zipcode, radius_km)
    try:
        result = fetcher.get(api_url, params=api_params, accept="json")
        listings = parse_api_response(result.text)
        if listings:
            return listings
        logger.warning("API path returned zero listings, falling back to HTML search page")
    except (RequestBudgetExceeded, RobotsDisallowed, BanDetected):
        raise
    except Exception as exc:
        logger.warning("API path failed (%s), falling back to HTML search page", exc)

    slug = quote(query.strip().lower().replace(" ", "-"))
    html_url = BASE_URL + SEARCH_HTML_PATH.format(query=slug)
    result = fetcher.get(html_url, accept="html")
    return parse_search_html(result.text)


def run(args: argparse.Namespace) -> dict:
    config = load_config(Path(args.config))

    log_path = Path(args.log_path or config.get("logging", {}).get("log_path", "logs/scraper.log"))
    setup_logging(log_path, debug=args.debug)

    db_path = args.db or config.get("storage", {}).get("db_path", "data/listings.db")
    max_requests = args.max_requests or config.get("request", {}).get("max_requests_per_run", 20)

    models = config.get("models", [])
    keywords = [args.query] if args.query else []
    keywords.extend(m for m in models if m.lower() != (args.query or "").lower())

    price_cfg = config.get("price", {})
    min_price = args.min_price if args.min_price is not None else price_cfg.get("min")
    max_price = args.max_price if args.max_price is not None else price_cfg.get("max")

    search_cfg = config.get("search", {})
    zipcode = args.zipcode or search_cfg.get("zipcode")
    radius = args.radius if args.radius is not None else search_cfg.get("radius_km")

    alert_threshold = config.get("alert", {}).get("price_below")

    logger.info(
        "Run start: query=%r keywords=%s price=[%s,%s] zipcode=%s radius=%s max_requests=%s",
        args.query, keywords, min_price, max_price, zipcode, radius, max_requests,
    )

    fetcher = Fetcher(max_requests_per_run=max_requests)

    try:
        raw_listings = fetch_listings(fetcher, args.query, zipcode, radius)
    except RobotsDisallowed as exc:
        logger.error("Stopping: %s", exc)
        return {"status": "robots_disallowed", "error": str(exc)}
    except BanDetected as exc:
        logger.error("Stopping: %s -- manual check needed before the next run", exc)
        return {"status": "manual_check_needed", "error": str(exc)}
    except RequestBudgetExceeded as exc:
        logger.warning("Stopping: %s", exc)
        return {"status": "budget_exceeded", "error": str(exc)}

    logger.info("Fetched %d raw listings in %d requests", len(raw_listings), fetcher.request_count)

    if args.dump_raw:
        Path(args.dump_raw).write_text(
            json.dumps([l.model_dump(mode="json") for l in raw_listings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    filtered = filter_listings(raw_listings, keywords, min_price, max_price)
    logger.info("%d/%d listings passed keyword+price filters", len(filtered), len(raw_listings))

    output_rows = []
    with Storage(db_path) as storage:
        for listing in filtered:
            enriched = None
            if args.enrich:
                enriched = enrich_description(listing.description_raw)

            upsert_info = storage.upsert_listing(listing, enriched=enriched)

            should_alert = (
                alert_threshold is not None
                and listing.price is not None
                and listing.price < alert_threshold
                and (upsert_info["status"] == "new" or upsert_info["price_changed"])
            )
            if should_alert:
                sent = notify_price_alert(listing, alert_threshold)
                if sent:
                    storage.mark_notified(listing.url)

            row = listing.model_dump(mode="json")
            row["enriched"] = enriched.model_dump() if enriched else None
            row["storage_status"] = upsert_info["status"]
            row["price_changed"] = upsert_info["price_changed"]
            row["alert_sent"] = bool(should_alert)
            output_rows.append(row)

    summary = {
        "status": "ok",
        "requests_made": fetcher.request_count,
        "raw_count": len(raw_listings),
        "filtered_count": len(filtered),
        "listings": output_rows,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote results to %s", args.output)

    logger.info("Run finished: %s", {k: v for k, v in summary.items() if k != "listings"})
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Marktplaats.nl laptop flipping scraper")
    p.add_argument("--query", required=True, help='Search query, e.g. "thinkpad t480"')
    p.add_argument("--max-price", type=float, default=None, help="Max price in EUR")
    p.add_argument("--min-price", type=float, default=None, help="Min price in EUR")
    p.add_argument("--zipcode", default=None, help="Dutch postcode to search around")
    p.add_argument("--radius", type=float, default=None, help="Search radius in km")
    p.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    p.add_argument("--db", default=None, help="Override SQLite DB path")
    p.add_argument("--log-path", default=None, help="Override log file path")
    p.add_argument("--max-requests", type=int, default=None, help="Override per-run request budget")
    p.add_argument("--enrich", action="store_true", help="Run Claude enrichment on filtered listings")
    p.add_argument("--output", default=None, help="Write JSON results to this file")
    p.add_argument("--dump-raw", default=None, help="Dump raw parsed (pre-filter) listings JSON here for debugging")
    p.add_argument("--debug", action="store_true", help="Verbose DEBUG logging (per-request UA/referer)")
    return p.parse_args(argv)


def main() -> None:
    load_dotenv()
    args = parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
