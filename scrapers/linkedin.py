"""
LinkedIn scraper (logged-out guest endpoints only).

Fixes vs v1:
  - Uses the public guest search endpoint that returns individual job CARDS
    (each with /jobs/view/<id> link), never the SERP listing page.
  - Extracts company from the card subtitle (v1 left 56/134 blank).
  - fetch_description(job) pulls the guest job-posting endpoint for the full
    description -> enables full-text scoring for top-N jobs.
  - clean_text() everywhere -> no more "802ComplianceAnalystjobsinBe".
  - On sustained 429 the scraper marks itself blocked and stops. No cookie
    sessions, no header rotation: that trades a rate limit for an account ban
    and a ToS violation. If you need volume, use an official API (Adzuna,
    JSearch) — see manager.py notes.
"""

import re
import logging
from urllib.parse import quote_plus

from .base import BaseScraper, clean_text, parse_posted_days, parse_salary

logger = logging.getLogger("litsearch.scrapers.linkedin")

SEARCH_URL = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/"
              "search?keywords={kw}&location={loc}&start={start}")
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

JOB_ID_RE = re.compile(r"/jobs/view/[^?]*?(\d{6,})")


class LinkedInScraper(BaseScraper):
    name = "linkedin"
    min_delay = 2.5  # guest API rate-limits hard; go slow

    def search(self, query: str, location: str = "", max_results: int = 10) -> list[dict]:
        jobs = []
        url = SEARCH_URL.format(kw=quote_plus(query),
                                loc=quote_plus(location or ""), start=0)
        soup = self.soup(self.polite_get(url))
        if soup is None:
            return jobs

        for card in soup.select("div.base-card, li")[: max_results * 2]:
            link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
            if not link or not link.get("href"):
                continue
            href = link["href"].split("?")[0]
            m = JOB_ID_RE.search(link["href"])
            title = clean_text(card.select_one(
                "h3.base-search-card__title, .base-search-card__title")) or clean_text(link)
            company = clean_text(card.select_one(
                "h4.base-search-card__subtitle, .base-search-card__subtitle a, "
                ".base-search-card__subtitle"))
            loc = clean_text(card.select_one(".job-search-card__location"))
            posted = clean_text(card.select_one("time"))
            salary = parse_salary(clean_text(card.select_one(
                ".job-search-card__salary-info")))

            if not title:
                continue
            jobs.append({
                "title": title,
                "company": company,
                "location": loc,
                "salary": salary,
                "url": href,
                "job_id": m.group(1) if m else "",
                "posted_days": parse_posted_days(posted),
                "description": "",
                "source": "LinkedIn",
            })
            if len(jobs) >= max_results:
                break
        return jobs

    def fetch_description(self, job: dict) -> bool:
        """Enrich one job with its full description. Returns True on success."""
        job_id = job.get("job_id")
        if not job_id:
            m = JOB_ID_RE.search(job.get("url", ""))
            job_id = m.group(1) if m else ""
        if not job_id:
            return False
        soup = self.soup(self.polite_get(DETAIL_URL.format(job_id=job_id)))
        if soup is None:
            return False
        desc = clean_text(soup.select_one(
            ".show-more-less-html__markup, .description__text"))
        if len(desc) >= 60:
            job["description"] = desc
            if not job.get("salary"):
                job["salary"] = parse_salary(desc)
            return True
        return False
