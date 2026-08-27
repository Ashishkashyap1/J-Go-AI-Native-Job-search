"""
LinkedIn Job Search API scraper (Fantastic Jobs via RapidAPI).

Provides full job descriptions, company info, and structured data from
LinkedIn listings — no anti-bot issues, no enrichment pass needed.

Setup:
  1. Subscribe to "LinkedIn Job Search" on RapidAPI (free tier available)
     https://rapidapi.com/fantastic-jobs-fantastic-jobs-default/api/linkedin-job-search-api
  2. Set env var: RAPIDAPI_KEY (same key works for multiple RapidAPI APIs)

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

API_URL = "https://linkedin-job-search-api.p.rapidapi.com/search"
API_HOST = "linkedin-job-search-api.p.rapidapi.com"


def _fmt_salary(j: dict) -> str:
    """Extract salary from API response if available."""
    lo = j.get("salary_min") or j.get("job_min_salary")
    hi = j.get("salary_max") or j.get("job_max_salary")
    if not lo and not hi:
        return ""
    try:
        if lo and hi:
            return f"{lo:,.0f} - {hi:,.0f}"
        return f"{(lo or hi):,.0f}"
    except (TypeError, ValueError):
        return str(lo or hi or "")


def _posted_days(j: dict):
    """Calculate age in days from posted date."""
    # Try various date fields
    for field in ("date_posted", "posted_at", "job_posted_at", "created_at"):
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
    """Scraper using Fantastic Jobs LinkedIn Job Search API on RapidAPI."""

    name = "linkedin-api"
    min_delay = 1.5  # be polite to the API

    def __init__(self, api_key: str = None, max_api_calls: int = 10):
        super().__init__()
        self.api_key = (
            api_key
            or os.environ.get("RAPIDAPI_KEY")
            or os.environ.get("JSEARCH_API_KEY")
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
            "query": query,
            "location": location or "",
            "page": 1,
        }

        # Inter-call delay
        wait = self.min_delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        try:
            resp = requests.get(API_URL, headers=self._headers, params=params, timeout=20)
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
            self.unavailable_reason = "not subscribed to LinkedIn Job Search API"
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
            # API may return list directly or wrapped in a key
            if isinstance(data, list):
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
                continue  # skip malformed entries
            title = (j.get("title") or j.get("job_title") or "").strip()
            url = (
                j.get("url")
                or j.get("apply_url")
                or j.get("job_apply_link")
                or j.get("link")
                or ""
            ).strip()
            if not title:
                continue

            company = (
                j.get("company")
                or j.get("company_name")
                or j.get("employer_name")
                or ""
            ).strip()
            loc = (
                j.get("location")
                or j.get("job_location")
                or ""
            ).strip()
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
            len(jobs),
            query,
            self.calls_made,
            self.max_api_calls,
        )
        return jobs
