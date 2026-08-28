"""
LinkedIn Job Search API scraper (Fresh LinkedIn Scraper via RapidAPI).

Provides full job descriptions, company info, and structured data from
LinkedIn listings — no anti-bot issues, no enrichment pass needed.

Setup:
  1. Subscribe to "Fresh LinkedIn Scraper API" on RapidAPI (free tier)
     https://rapidapi.com/fantastic-jobs-fantastic-jobs-default/api/fresh-linkedin-scraper-api
  2. Set env var: RAPIDAPI_KEY

Design rules (same as base.py): official endpoint, honest auth, no evasion.
429 = quota exhausted -> mark blocked, stop, report.
"""

import os
import time
import logging
from datetime import datetime, timezone

import requests

from .base import BaseScraper

logger = logging.getLogger("litsearch.scrapers.linkedin_jobs_api")

API_HOST = "fresh-linkedin-scraper-api.p.rapidapi.com"
SEARCH_URL = f"https://{API_HOST}/api/v1/job/search"
DETAIL_URL = f"https://{API_HOST}/api/v1/job/detail"

# Map freshness days to API date_posted param
FRESHNESS_MAP = {
    1: "past_24_hours",
    3: "past_24_hours",
    7: "past_week",
    14: "past_week",
    30: "past_month",
}


def _fmt_salary(j: dict) -> str:
    """Extract salary from API response if available."""
    salary = j.get("salary") or {}
    if isinstance(salary, dict):
        lo = salary.get("min_salary")
        hi = salary.get("max_salary")
        currency = salary.get("currency", "")
        if lo or hi:
            parts = []
            if lo:
                parts.append(f"{currency}{lo:,.0f}" if currency else f"{lo:,.0f}")
            if hi:
                parts.append(f"{currency}{hi:,.0f}" if currency else f"{hi:,.0f}")
            return " - ".join(parts) if parts else ""
    return ""


def _posted_days(j: dict) -> None:
    """Calculate age in days from posted date."""
    for field in ("listed_at", "original_listed_at", "date_posted", "posted_at"):
        val = j.get(field)
        if not val:
            continue
        try:
            if isinstance(val, (int, float)):
                posted = datetime.fromtimestamp(int(val), tz=timezone.utc)
            else:
                posted = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - posted).total_seconds() / 86400
            return round(max(age, 0.0), 1)
        except (ValueError, OSError, OverflowError, TypeError):
            continue
    return None


class LinkedInJobsAPIScraper(BaseScraper):
    """Scraper using Fresh LinkedIn Scraper API on RapidAPI."""

    name = "linkedin-api"
    min_delay = 1.5

    def __init__(self, api_key: str = None, max_api_calls: int = 10):
        super().__init__()
        self.api_key = (
            api_key
            or os.environ.get("RAPIDAPI_KEY")
            or os.environ.get("LINKEDIN_API_KEY")
        )
        self.max_api_calls = max_api_calls
        self.calls_made = 0
        self.available = bool(self.api_key)
        self.unavailable_reason = "set RAPIDAPI_KEY env var"
        if not self.available:
            logger.error(
                "linkedin-api: no API key found (RAPIDAPI_KEY). Portal will report UNAVAILABLE."
            )
        self._headers = {
            "X-RapidAPI-Key": self.api_key or "",
            "X-RapidAPI-Host": API_HOST,
        }

    def search(self, query: str, location: str = "", max_results: int = 10) -> list[dict]:
        if not self.available or self.blocked:
            return []
        if self.calls_made >= self.max_api_calls:
            if self.calls_made == self.max_api_calls:
                logger.warning(
                    "linkedin-api: per-run API call cap (%d) reached — skipping.",
                    self.max_api_calls,
                )
                self.calls_made += 1
            return []

        params = {
            "keyword": query,
            "page": 1,
            "sort_by": "recent",
        }

        # Inter-call delay
        wait = self.min_delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        try:
            resp = requests.get(SEARCH_URL, headers=self._headers, params=params, timeout=20)
            self._last_request = time.time()
            self.calls_made += 1
        except requests.RequestException as e:
            logger.warning("linkedin-api: request error on %r: %s", query, e)
            return []

        if resp.status_code in (401, 403):
            logger.error(
                "linkedin-api: HTTP %s — not subscribed. Marking BLOCKED.", resp.status_code
            )
            self.blocked = True
            self.unavailable_reason = "not subscribed to Fresh LinkedIn Scraper API on RapidAPI"
            return []
        if resp.status_code == 429:
            logger.error("linkedin-api: HTTP 429 — quota exhausted. Marking BLOCKED.")
            self.blocked = True
            return []
        if resp.status_code == 404:
            logger.warning("linkedin-api: endpoint not found. Marking BLOCKED.")
            self.blocked = True
            return []
        if resp.status_code != 200:
            logger.warning(
                "linkedin-api: HTTP %s on %r: %.200s", resp.status_code, query, resp.text
            )
            return []

        try:
            data = resp.json()
            # Fresh LinkedIn Scraper API wraps in {"success": true, "data": [...]}
            if isinstance(data, dict) and data.get("success"):
                jobs_raw = data.get("data") or []
            elif isinstance(data, list):
                jobs_raw = data
            elif isinstance(data, dict):
                jobs_raw = data.get("data") or data.get("jobs") or data.get("results") or []
            else:
                jobs_raw = []
        except ValueError:
            logger.warning("linkedin-api: non-JSON response on %r", query)
            return []

        jobs = []
        for j in jobs_raw:
            if isinstance(j, str):
                continue

            title = (j.get("title") or j.get("job_title") or "").strip()
            url = (
                j.get("url")
                or j.get("job_url")
                or j.get("apply_url")
                or j.get("job_apply_link")
                or j.get("link")
                or ""
            ).strip()
            if not title:
                continue

            # Company info (may be nested object or flat string)
            company_raw = j.get("company") or j.get("company_name") or j.get("employer_name") or ""
            if isinstance(company_raw, dict):
                company = company_raw.get("name", "").strip()
            else:
                company = str(company_raw).strip()

            # Location (may be nested or flat)
            loc = (
                j.get("location")
                or j.get("job_location")
                or ""
            ).strip()

            # Description (full text available in API!)
            desc = (
                j.get("description")
                or j.get("job_description")
                or ""
            ).strip()

            salary = _fmt_salary(j)

            jobs.append(
                {
                    "title": title,
                    "company": company,
                    "location": loc,
                    "salary": salary,
                    "url": url,
                    "posted_days": _posted_days(j),
                    "description": desc,
                    "source": "LinkedIn API",
                }
            )
            if len(jobs) >= max_results:
                break

        logger.info(
            "linkedin-api: %d jobs for %r (call %d/%d).",
            len(jobs), query,
            self.calls_made, self.max_api_calls,
        )
        return jobs
