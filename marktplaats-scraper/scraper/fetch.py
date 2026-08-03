"""HTTP client for marktplaats.nl with rate limiting, UA rotation, retry/backoff
and ban/captcha handling.

Design notes
------------
Marktplaats' search page is a server-rendered Next.js app. There are two ways
to get structured data out of it without a headless browser:

1. The internal JSON endpoint the frontend itself calls for search results:
   GET https://www.marktplaats.nl/lrp/api/search?query=...&l1CategoryId=...
   This is undocumented, can change shape/headers requirements at any time,
   and may require anti-bot tokens the plain requests session doesn't have.

2. The HTML search page itself embeds the exact same data Next.js hydrates
   the page with, inside a <script id="__NEXT_DATA__" type="application/json">
   tag. This is guaranteed to exist on any working page render (it's how
   Next.js SSR works) and needs no special headers beyond a normal browser
   request, so it's the more robust primary path. scraper/parse.py knows how
   to read both shapes.

This module tries (1) first (cheap, one request) and falls back to (2) if the
API call fails for a non-ban reason (schema drift, 404, etc). Field names in
parse.py are written defensively for exactly this reason -- verify them
against a real captured response (see README) and adjust if Marktplaats has
changed something.
"""
from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger("scraper.fetch")

BASE_URL = "https://www.marktplaats.nl"
SEARCH_API_PATH = "/lrp/api/search"
SEARCH_HTML_PATH = "/q/{query}/"

MAX_REQUESTS_PER_RUN_DEFAULT = 20
MIN_DELAY_SECONDS = 3.0
MAX_DELAY_SECONDS = 7.0
RETRY_BACKOFF_SCHEDULE = (30, 60, 120)  # seconds, exponential-ish, 3 attempts
BAN_COOLDOWN_RANGE = (15 * 60, 30 * 60)  # 15-30 min, one retry after a 403/429/captcha
REQUEST_TIMEOUT = 15

# A small but current spread of real browser/OS UA strings (Chrome/Firefox/Safari
# across Windows/macOS/Linux). Rotate randomly per request -- not meant to be
# exhaustive, just avoid a single fixed fingerprint.
USER_AGENTS = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Firefox / Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Safari/605.1.15",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    # Chrome / Android (mobile share of traffic looks realistic too)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Mobile Safari/537.36",
]

CAPTCHA_MARKERS = (
    "datadome",
    "px-captcha",
    "perimeterx",
    "captcha",
    "unusual traffic",
    "even geduld",  # "please wait" interstitial, Dutch
    "toegang geweigerd",  # "access denied", Dutch
    "access denied",
    "checking your browser",
    "please verify you are a human",
)


class BanDetected(Exception):
    """Raised when marktplaats.nl kept blocking us even after the cooldown retry."""


class RequestBudgetExceeded(Exception):
    """Raised when a run tries to exceed max_requests_per_run."""


class RobotsDisallowed(Exception):
    """Raised when robots.txt forbids fetching the requested path."""


def looks_like_captcha_or_block(status_code: int, text: str) -> bool:
    if status_code in (403, 429):
        return True
    if status_code == 503:
        return True
    lowered = (text or "")[:5000].lower()
    return any(marker in lowered for marker in CAPTCHA_MARKERS)


class RobotsGate:
    """Fetches and caches robots.txt once per run, fails closed on error."""

    def __init__(self, base_url: str = BASE_URL, user_agent: str = "*"):
        self.base_url = base_url
        self.user_agent = user_agent
        self._rp = RobotFileParser()
        self._loaded = False
        self._load()

    def _load(self) -> None:
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            resp = requests.get(
                robots_url,
                headers={"User-Agent": random.choice(USER_AGENTS)},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            self._rp.parse(resp.text.splitlines())
            self._loaded = True
            logger.info("robots.txt loaded from %s", robots_url)
        except requests.RequestException as exc:
            logger.error(
                "Could not fetch/parse robots.txt (%s) -- failing closed, "
                "no requests will be made this run",
                exc,
            )
            self._loaded = False

    def can_fetch(self, path: str) -> bool:
        if not self._loaded:
            return False
        url = urljoin(self.base_url, path)
        return self._rp.can_fetch(self.user_agent, url)


@dataclass
class FetchResult:
    status_code: int
    url: str
    text: str
    headers: dict = field(default_factory=dict)
    is_json: bool = False


class Fetcher:
    """Sequential, paced, rate-limited HTTP client for marktplaats.nl.

    Never issues concurrent requests -- one request at a time, with a random
    3-7s pause between them, a hard cap on total requests per run, retry with
    exponential backoff on transient errors, and a single long cooldown retry
    on 403/429/captcha before giving up cleanly.
    """

    def __init__(
        self,
        max_requests_per_run: int = MAX_REQUESTS_PER_RUN_DEFAULT,
        proxy_url: Optional[str] = None,
        robots_gate: Optional[RobotsGate] = None,
    ):
        self.session = requests.Session()
        self.max_requests_per_run = max_requests_per_run
        self.request_count = 0
        # First request of a run looks like it came from a Google search,
        # which is a very common, unremarkable entry point -- never send an
        # empty Referer.
        self.last_referer = "https://www.google.com/"
        self.robots = robots_gate or RobotsGate()

        proxy_url = proxy_url or os.environ.get("PROXY_URL") or None
        if proxy_url:
            logger.info("Using proxy for requests (PROXY_URL set)")
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

    # -- public API ---------------------------------------------------

    def get(self, url: str, params: Optional[dict] = None, accept: str = "html") -> FetchResult:
        """Fetch a single URL, respecting robots.txt, budget, pacing and retries."""
        if self.request_count >= self.max_requests_per_run:
            raise RequestBudgetExceeded(
                f"Request budget of {self.max_requests_per_run} exhausted for this run"
            )

        path = url[len(BASE_URL):] if url.startswith(BASE_URL) else url
        if not self.robots.can_fetch(path):
            logger.error("robots.txt disallows fetching %s -- aborting this request", path)
            raise RobotsDisallowed(f"robots.txt disallows {path}")

        if self.request_count > 0:
            self._pace()

        result = self._request_with_retry(url, params=params, accept=accept)
        self.request_count += 1
        self.last_referer = result.url
        return result

    # -- internals ------------------------------------------------------

    def _pace(self) -> None:
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        logger.info("Pacing: sleeping %.1fs before next request", delay)
        time.sleep(delay)

    def _headers(self, accept: str) -> dict:
        ua = random.choice(USER_AGENTS)
        logger.debug("Using User-Agent=%r Referer=%r", ua, self.last_referer)
        accept_header = (
            "application/json, text/plain, */*"
            if accept == "json"
            else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        )
        headers = {
            "User-Agent": ua,
            "Accept": accept_header,
            "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": self.last_referer,
            "Connection": "keep-alive",
        }
        if accept == "html":
            headers.update(
                {
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin" if BASE_URL in self.last_referer else "cross-site",
                    "Sec-Fetch-Dest": "document",
                }
            )
        else:
            headers["X-Requested-With"] = "XMLHttpRequest"
        return headers

    def _request_with_retry(self, url: str, params: Optional[dict], accept: str) -> FetchResult:
        last_exc: Optional[Exception] = None
        for attempt, wait_s in enumerate((0, *RETRY_BACKOFF_SCHEDULE)):
            if wait_s:
                logger.warning("Retry attempt %d for %s -- backing off %ds", attempt, url, wait_s)
                time.sleep(wait_s)
            try:
                resp = self.session.get(
                    url, params=params, headers=self._headers(accept), timeout=REQUEST_TIMEOUT
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Request error on attempt %d for %s: %s", attempt, url, exc)
                continue

            if looks_like_captcha_or_block(resp.status_code, resp.text):
                logger.warning(
                    "BAN_SIGNAL status=%s url=%s len=%d -- treating as block/captcha",
                    resp.status_code,
                    url,
                    len(resp.text or ""),
                )
                return self._handle_ban(url, params, accept)

            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"{resp.status_code} for {url}")
                logger.warning("Server error %s on attempt %d for %s", resp.status_code, attempt, url)
                continue

            resp.raise_for_status()
            return FetchResult(
                status_code=resp.status_code,
                url=resp.url,
                text=resp.text,
                headers=dict(resp.headers),
                is_json="application/json" in resp.headers.get("Content-Type", ""),
            )

        raise last_exc or RuntimeError(f"Failed to fetch {url} after retries")

    def _handle_ban(self, url: str, params: Optional[dict], accept: str) -> FetchResult:
        """One long cooldown + single retry, per spec. Never loops or hammers."""
        cooldown = random.uniform(*BAN_COOLDOWN_RANGE)
        logger.warning(
            "BAN_SIGNAL cooling down for %.0fs (%.1f min) before a single retry",
            cooldown,
            cooldown / 60,
        )
        time.sleep(cooldown)
        resp = self.session.get(
            url, params=params, headers=self._headers(accept), timeout=REQUEST_TIMEOUT
        )
        if looks_like_captcha_or_block(resp.status_code, resp.text):
            logger.error(
                "MANUAL_CHECK_NEEDED: still blocked (status=%s) after cooldown retry on %s. "
                "Stopping this run cleanly -- do not retry automatically, check the site by "
                "hand before running again.",
                resp.status_code,
                url,
            )
            raise BanDetected(f"Still blocked after cooldown retry: {url}")
        logger.info("Cooldown retry succeeded, resuming normal operation")
        return FetchResult(
            status_code=resp.status_code,
            url=resp.url,
            text=resp.text,
            headers=dict(resp.headers),
            is_json="application/json" in resp.headers.get("Content-Type", ""),
        )
