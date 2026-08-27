"""
JSearch (RapidAPI) scraper — official API portal for LITSEARCH v2.

Why this exists: naukri/indeed/glassdoor/foundit are BLOCKED by enterprise
anti-bot (correctly detected and respected by browser.py). JSearch queries
the Google-for-Jobs index, which carries most of those portals' inventory,
WITH full descriptions — so these jobs score on a full-text basis
immediately, no enrich_descriptions() pass needed.

SETUP
-----
1. Free RapidAPI account -> subscribe "JSearch" (Basic free plan).
2. Set env var:  RAPIDAPI_KEY  (or JSEARCH_API_KEY)
3. Already registered in manager.py / cli.py as portal name "jsearch".

QUOTA
-----
Free tier is small (~200 requests/month; confirm on your RapidAPI
dashboard). Each search() call = 1 request. The manager calls search()
once per query, so `max_api_calls` caps spend per run (default 8).

Design rules (same as base.py): official endpoint, honest auth, no
evasion. 429 = quota exhausted -> mark blocked, stop, report.
"""

import os
import time
import logging
from datetime import datetime, timezone

import requests

from .base import BaseScraper

logger = logging.getLogger("litsearch.scrapers.jsearch")

API_URL = "https://jsearch.p.rapidapi.com/search"
API_HOST = "jsearch.p.rapidapi.com"


def _fmt_salary(j: dict) -> str:
    lo, hi = j.get("job_min_salary"), j.get("job_max_salary")
    if not lo and not hi:
        return ""
    cur = j.get("job_salary_currency") or ""
    per = j.get("job_salary_period") or ""
    try:
        rng = (f"{lo:,.0f}-{hi:,.0f}" if lo and hi else f"{(lo or hi):,.0f}")
    except (TypeError, ValueError):
        rng = f"{lo or hi}"
    out = f"{cur} {rng}"
    if per:
        out += f" / {per.lower()}"
    return out.strip()


def _posted_days(j: dict):
    """UTC timestamp -> age in days (float), for the freshness filter."""
    ts = j.get("job_posted_at_timestamp")
    if not ts:
        return None
    try:
        posted = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, OSError, OverflowError, TypeError):
        return None
    age = (datetime.now(timezone.utc) - posted).total_seconds() / 86400
    return round(max(age, 0.0), 1)


class JSearchScraper(BaseScraper):
    name = "jsearch"
    min_delay = 1.0          # polite even to APIs

    def __init__(self, api_key: str = None, country: str = None,
                 max_api_calls: int = 8):
        super().__init__()
        self.api_key = (api_key
                        or os.environ.get("RAPIDAPI_KEY")
                        or os.environ.get("JSEARCH_API_KEY"))
        self.country = country or os.environ.get("JSEARCH_COUNTRY", "in")
        self.max_api_calls = max_api_calls
        self.calls_made = 0
        # Manager reads these two for portal_status:
        self.available = bool(self.api_key)
        self.unavailable_reason = "set RAPIDAPI_KEY env var"
        if not self.available:
            logger.error("jsearch: no API key found (RAPIDAPI_KEY / "
                         "JSEARCH_API_KEY). Portal will report UNAVAILABLE.")
        # Independent auth headers; do NOT reuse base HTML headers.
        self._headers = {
            "X-RapidAPI-Key": self.api_key or "",
            "X-RapidAPI-Host": API_HOST,
        }

    # ------------------------------------------------------------------ #
    def search(self, query: str, location: str = "",
               max_results: int = 10) -> list[dict]:
        if not self.available or self.blocked:
            return []
        if self.calls_made >= self.max_api_calls:
            if self.calls_made == self.max_api_calls:
                logger.warning("jsearch: per-run API call cap (%d) reached — "
                               "skipping remaining queries to protect quota.",
                               self.max_api_calls)
                self.calls_made += 1  # log once
            return []

        q = f"{query} in {location}" if location else query
        params = {
            "query": q,
            "page": 1,
            "num_pages": 1,          # 1 page ≈ 10 jobs; keep quota cheap
            "country": self.country,
            "date_posted": "month",  # freshness_days does finer filtering
        }

        # Inter-call delay (session-independent API, so simple sleep):
        wait = self.min_delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(API_URL, headers=self._headers, params=params,
                                timeout=20)
            self._last_request = time.time()
            self.calls_made += 1
        except requests.RequestException as e:
            logger.warning("jsearch: request error on %r: %s", q, e)
            return []

        if resp.status_code in (401, 403):
            logger.error("jsearch: HTTP %s — invalid key or not subscribed "
                         "to the JSearch API. Marking BLOCKED.",
                         resp.status_code)
            self.blocked = True
            return []
        if resp.status_code == 429:
            logger.error("jsearch: HTTP 429 — monthly quota exhausted. "
                         "Marking BLOCKED for this run.")
            self.blocked = True
            return []
        if resp.status_code != 200:
            logger.warning("jsearch: HTTP %s on %r: %.200s",
                           resp.status_code, q, resp.text)
            return []

        try:
            data = resp.json().get("data") or []
        except ValueError:
            logger.warning("jsearch: non-JSON response on %r", q)
            return []

        jobs = []
        for j in data:
            url = (j.get("job_apply_link") or "").strip()
            title = (j.get("job_title") or "").strip()
            if not url or not title:
                continue                      # checker would reject anyway
            loc = ", ".join(x for x in (j.get("job_city"),
                                        j.get("job_state"),
                                        j.get("job_country")) if x)
            publisher = (j.get("job_publisher") or "").strip()
            jobs.append({
                "title": title,
                "company": (j.get("employer_name") or "").strip(),
                "location": loc,
                "salary": _fmt_salary(j),
                "url": url,
                "job_id": j.get("job_id") or "",
                "posted_days": _posted_days(j),
                "description": (j.get("job_description") or "").strip(),
                "source": f"JSearch ({publisher})" if publisher else "JSearch",
            })
            if len(jobs) >= max_results:
                break

        logger.info("jsearch: %d jobs for %r (call %d/%d).",
                    len(jobs), q, self.calls_made, self.max_api_calls)
        return jobs
