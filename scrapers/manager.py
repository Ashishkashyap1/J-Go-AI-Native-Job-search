"""
ScraperManager v2 - orchestrates scrapers, portal health, freshness filter,
and description enrichment for top-N candidates.

Key changes vs v1:
  - No silent zeros: portal status (OK / BLOCKED / UNAVAILABLE / SELECTOR-MISS
    suspected) is collected and returned for the checker/QC report.
  - enrich_descriptions(): after checker + first-pass scoring, fetch full
    descriptions for the top-N jobs only (cheap, targeted), then re-score.
    This is what moves scoring from "title-only" to "full-text".
  - freshness_days: drop jobs older than N days when the portal exposes age.
  - DuckDuckGo scraper is GONE. It produced SERP links, not jobs. If you want
    discovery breadth, wire an official API instead (Adzuna has a free tier:
    https://developer.adzuna.com/ ; JSearch via RapidAPI covers Indeed/
    LinkedIn/Glassdoor aggregated, with descriptions included and no anti-bot
    war). An API scraper is ~40 lines against this same interface.
"""

import logging

from .linkedin import LinkedInScraper
from .jsearch import JSearchScraper
from .browser import (HAS_PLAYWRIGHT, NaukriScraper, IndeedScraper,
                      ShineScraper, FounditScraper, GlassdoorScraper)

logger = logging.getLogger("litsearch.scrapers.manager")

DEFAULT_PORTALS = ["linkedin", "jsearch", "naukri", "indeed", "shine", "foundit", "glassdoor"]

SCRAPER_CLASSES = {
    "linkedin": LinkedInScraper,
    "jsearch": JSearchScraper,
    "naukri": NaukriScraper,
    "indeed": IndeedScraper,
    "shine": ShineScraper,
    "foundit": FounditScraper,
    "glassdoor": GlassdoorScraper,
}


class ScraperManager:
    def __init__(self, portals: list[str] = None):
        portals = portals or DEFAULT_PORTALS
        self.scrapers = {}
        for p in portals:
            cls = SCRAPER_CLASSES.get(p)
            if cls is None:
                logger.warning("Unknown portal '%s' — skipped", p)
                continue
            self.scrapers[p] = cls()
        if not HAS_PLAYWRIGHT and any(
                p in self.scrapers for p in
                ("naukri", "indeed", "shine", "foundit", "glassdoor")):
            logger.warning(
                "Playwright not installed: naukri/indeed/shine/foundit/glassdoor "
                "will return 0. Fix: pip install playwright && playwright install chromium")

    def search_all(self, queries: list[str], location: str = "",
                   max_results: int = 10, freshness_days: int = None) -> tuple[list, dict, dict]:
        """
        Run all queries across all scrapers.

        Returns (all_jobs, portal_counts, portal_status).
        portal_status values: OK | BLOCKED | UNAVAILABLE | ZERO-RESULTS
        """
        all_jobs, portal_counts = [], {p: 0 for p in self.scrapers}
        for query in queries:
            for name, scraper in self.scrapers.items():
                if getattr(scraper, "blocked", False):
                    continue
                try:
                    jobs = scraper.search(query, location, max_results=max_results)
                except Exception as e:
                    logger.warning("Scraper %s failed on '%s': %s", name, query, e)
                    continue
                if freshness_days is not None:
                    jobs = [j for j in jobs
                            if j.get("posted_days") is None
                            or j["posted_days"] <= freshness_days]
                all_jobs.extend(jobs)
                portal_counts[name] += len(jobs)

        portal_status = {}
        for name, scraper in self.scrapers.items():
            if not getattr(scraper, "available", True):
                portal_status[name] = ("UNAVAILABLE (" + getattr(scraper, "unavailable_reason", "install Playwright") + ")")
            elif getattr(scraper, "blocked", False):
                portal_status[name] = "BLOCKED (403/429/CAPTCHA — respected)"
            elif portal_counts.get(name, 0) == 0:
                portal_status[name] = "ZERO-RESULTS (check SELECTOR MISS warnings)"
            else:
                portal_status[name] = "OK"
        return all_jobs, portal_counts, portal_status

    def enrich_descriptions(self, jobs: list[dict], top_n: int = 20) -> int:
        """
        Fetch full descriptions for the top-N jobs (call AFTER first scoring
        pass so N is spent on the best candidates). Returns count enriched.
        Re-score afterwards: rank_jobs(cv_data, jobs).
        """
        li = self.scrapers.get("linkedin")
        enriched = 0
        for job in jobs[:top_n]:
            desc = (job.get("description") or "").strip()
            if desc and desc.upper() != "N/A" and len(desc) >= 60:
                continue
            ok = False
            if job.get("source") == "LinkedIn" and li is not None:
                ok = li.fetch_description(job)
            # Browser portals: card snippet already captured where available;
            # per-job detail fetch for them is a follow-up (needs live selector
            # verification per portal detail page).
            if ok:
                enriched += 1
        return enriched

    def close(self):
        for s in self.scrapers.values():
            close = getattr(s, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass
