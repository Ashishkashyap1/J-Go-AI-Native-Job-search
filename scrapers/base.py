"""
Base scraper - polite HTTP, backoff, shared text utilities.

Design rules:
  - One realistic browser header set. No user-agent rotation, no credentialed
    sessions: this tool stays on public, logged-out pages only.
  - Rate limiting is respected, not evaded: 429 -> exponential backoff, then
    give up and report. Per-request delay between calls.
  - All text extraction uses get_text(" ", strip=True) — fixes the
    "802ComplianceAnalystjobsinBe" word-fusion bug.
"""

import re
import time
import random
import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("litsearch.scrapers")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SALARY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s?[\d,.]+(?:\s?(?:lpa|lakhs?|l|k|cr))?"
    r"(?:\s?[-–to]+\s?(?:₹|rs\.?|inr)?\s?[\d,.]+(?:\s?(?:lpa|lakhs?|l|k|cr))?)?"
    r"(?:\s?(?:per\s+(?:annum|month|year)|p\.?a\.?|/yr|/mo))?",
    re.IGNORECASE,
)

POSTED_RE = re.compile(
    r"(\d+)\s*(hour|hr|day|week|month)s?\s*ago|just\s+posted|today|yesterday",
    re.IGNORECASE,
)


def clean_text(node) -> str:
    """BeautifulSoup node -> whitespace-normalized text (no word fusion)."""
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_salary(text: str) -> str:
    m = SALARY_RE.search(text or "")
    return m.group().strip() if m else ""


def parse_posted_days(text: str):
    """Return approx age in days, or None if not stated."""
    m = POSTED_RE.search(text or "")
    if not m:
        return None
    if m.group(0).lower() in ("just posted", "today"):
        return 0
    if m.group(0).lower() == "yesterday":
        return 1
    n, unit = int(m.group(1)), m.group(2).lower()
    factor = {"hour": 1 / 24, "hr": 1 / 24, "day": 1, "week": 7, "month": 30}[unit]
    return round(n * factor, 1)


class BaseScraper:
    """HTTP scraper base with polite delays and 429/403 backoff."""

    name = "base"
    min_delay = 1.5     # seconds between requests
    max_retries = 3

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0.0
        self.blocked = False   # set True after repeated 403/429 -> manager reports it

    def polite_get(self, url: str, **kwargs) -> requests.Response | None:
        """GET with inter-request delay and exponential backoff on 429/403."""
        if self.blocked:
            return None
        for attempt in range(self.max_retries):
            wait = self.min_delay - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.5))
            try:
                resp = self.session.get(url, timeout=15, **kwargs)
                self._last_request = time.time()
            except requests.RequestException as e:
                logger.warning("%s: request error %s (%s)", self.name, e, url)
                return None
            if resp.status_code == 200:
                return resp
            if resp.status_code in (403, 429):
                backoff = 2 ** attempt * 5
                logger.warning("%s: HTTP %s, backing off %ss (attempt %s/%s)",
                               self.name, resp.status_code, backoff,
                               attempt + 1, self.max_retries)
                time.sleep(backoff)
                continue
            logger.warning("%s: HTTP %s for %s", self.name, resp.status_code, url)
            return None
        # Exhausted retries on 403/429 -> mark portal blocked, stop hammering
        self.blocked = True
        logger.error("%s: marked BLOCKED after repeated 403/429 — respecting the block.",
                     self.name)
        return None

    def soup(self, resp) -> BeautifulSoup | None:
        return BeautifulSoup(resp.text, "lxml") if resp is not None else None

    def search(self, query: str, location: str = "", max_results: int = 10) -> list[dict]:
        raise NotImplementedError
