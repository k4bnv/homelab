"""Offline, fully mocked end-to-end demo of the scraper pipeline.

This sandbox's network policy blocks outbound connections to marktplaats.nl,
so this script monkeypatches requests.get / requests.Session.get with a
realistic fixture (robots.txt + the API-empty->HTML-__NEXT_DATA__-fallback
path) and runs the *real* main.run() pipeline (fetch pacing/backoff logic,
parse.py, filters.py, storage.py upsert, notify.py stub) against it end to
end, so the logging/pacing/JSON-shape behaviour you see here is real, only
the HTTP transport is faked. Claude enrichment is also faked (no live
ANTHROPIC_API_KEY/network here) but goes through the real LaptopSpecs model.

Run for real once this project is on a machine that can reach
marktplaats.nl: `python main.py --query "laptop" --output results.json`.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import main as main_module
from scraper.enrich import LaptopSpecs
from scraper.fetch import BASE_URL

FIXTURES = Path(__file__).parent / "fixtures"

ROBOTS_TXT = """User-agent: *
Disallow: /account/
Disallow: /my/
Disallow: /verkopen/
Allow: /lrp/api/search
Allow: /q/
Sitemap: https://www.marktplaats.nl/sitemap.xml
"""

CALL_LOG: list[tuple[str, dict | None]] = []


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, url: str = "", headers: dict | None = None):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {self.url}")


def fake_requests_get(url, headers=None, timeout=None, **kwargs):
    """Stands in for RobotsGate's plain requests.get(robots.txt)."""
    return FakeResponse(ROBOTS_TXT, 200, url)


def fake_session_get(self, url, params=None, headers=None, timeout=None, **kwargs):
    """Stands in for Fetcher's self.session.get(...)."""
    CALL_LOG.append((url, params))
    if url == BASE_URL + "/lrp/api/search":
        # Simulate the internal API returning an empty page for this query,
        # to also exercise the __NEXT_DATA__ HTML fallback path in the same demo run.
        return FakeResponse(json.dumps({"listings": []}), 200, url, {"Content-Type": "application/json"})
    if url.startswith(BASE_URL + "/q/"):
        html = (FIXTURES / "sample_next_data.html").read_text(encoding="utf-8")
        return FakeResponse(html, 200, url, {"Content-Type": "text/html; charset=utf-8"})
    raise AssertionError(f"Unexpected URL requested in demo: {url}")


def fake_enrich_description(description_raw, **kwargs):
    """Stands in for scraper.enrich.enrich_description -- same LaptopSpecs
    model, but rule-based instead of a live Claude API call."""
    if not description_raw:
        return None
    text = description_raw.lower()
    note = "MOCK ENRICH (no live ANTHROPIC_API_KEY / network in this sandbox demo)"
    if "x1 carbon" in text or "strepen" in text or "onderdelen" in text:
        return LaptopSpecs(
            cpu="Intel Core i7 (8th gen)",
            ram_gb=16,
            ssd_gb=512,
            screen='14" (resolution not stated)',
            likely_defects=[
                "screen shows vertical lines (possible cable/panel fault)",
                "battery holds ~20 minutes only (needs replacement)",
                "sold as-is for parts/repair -- not fully functional",
            ],
            confidence_notes=note,
        )
    if "t480" in text:
        return LaptopSpecs(
            cpu="Intel Core i5-8350U",
            ram_gb=16,
            ssd_gb=256,
            screen='14" FHD',
            likely_defects=["small scratch on the lid (cosmetic only)"],
            confidence_notes=note,
        )
    return LaptopSpecs(likely_defects=[], confidence_notes=note)


def main() -> None:
    with mock.patch("requests.get", side_effect=fake_requests_get), \
         mock.patch("requests.Session.get", new=fake_session_get), \
         mock.patch.object(main_module, "enrich_description", new=fake_enrich_description):
        args = main_module.parse_args(
            [
                "--query", "laptop",
                "--config", "config.yaml",
                "--db", "data/demo_listings.db",
                "--log-path", "logs/demo_run.log",
                "--output", "demo_results.json",
                "--enrich",
                "--debug",
            ]
        )
        summary = main_module.run(args)

    print("\n=== RUN SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "listings"}, indent=2, ensure_ascii=False))

    print(f"\n=== HTTP CALLS MADE ({len(CALL_LOG)}) ===")
    for i, (url, params) in enumerate(CALL_LOG, 1):
        print(f"  {i}. GET {url} params={params}")

    print("\n=== FILTERED + STORED LISTINGS (data/demo_results.json) ===")
    print(json.dumps(summary["listings"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
