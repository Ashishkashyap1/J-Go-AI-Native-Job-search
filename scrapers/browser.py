"""
Playwright-based scrapers for JS-heavy portals: Naukri, Indeed, Shine,
Foundit, Glassdoor.

Requires:  pip install playwright && playwright install chromium
If Playwright is missing, these scrapers deactivate and the manager reports
them as UNAVAILABLE (never silently zero).

WARNING [selector confidence: Guessing]: CSS selectors below are from known
page structures but portals redesign frequently. Each scraper logs a
"SELECTOR MISS" warning when a page loads but yields 0 cards — that is your
signal to update selectors, not a scraper crash.

Scope boundary: these scrapers render public pages in a real browser. They do
NOT solve CAPTCHAs, do not log in, and back off on block pages. If a portal
serves a CAPTCHA wall, the honest fix is that portal's official API/feed, not
an evasion arms race.
"""

import time
import json
import random
import logging
import subprocess
import sys
import os

from .base import clean_text, parse_salary, parse_posted_days

logger = logging.getLogger("litsearch.scrapers.browser")

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# Script that runs in a subprocess — avoids asyncio-loop conflict with Rich
_BROWSE_SCRIPT = '''
import sys, json, time, random
from playwright.sync_api import sync_playwright

def run(url, wait_selector, min_delay):
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1366, "height": 850}, locale="en-IN")
    page = ctx.new_page()
    try:
        page.goto(url, timeout=30000)
        try:
            page.wait_for_selector(wait_selector, timeout=12000)
        except Exception:
            body = (page.content() or "").lower()
            if any(t in body for t in ("captcha", "unusual traffic", "access denied", "are you a human")):
                return {"status": "BLOCKED", "html": ""}
            return {"status": "SELECTOR_MISS", "html": page.content()[:500]}
        time.sleep(1.0 + random.uniform(0, 1.0))
        html = page.content()
        time.sleep(min_delay)
        return {"status": "OK", "html": html}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "html": ""}
    finally:
        ctx.close()
        browser.close()
        pw.stop()

if __name__ == "__main__":
    url, wait_sel, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
    result = run(url, wait_sel, delay)
    print(json.dumps(result))
'''


class BrowserScraper:
    """Shared Playwright plumbing. Subclasses define build_url() + parse()."""

    name = "browser"
    wait_selector = "body"
    min_delay = 3.0

    def __init__(self):
        self.available = HAS_PLAYWRIGHT
        self.blocked = False

    # -- lifecycle -----------------------------------------------------------
    def close(self):
        pass  # no persistent browser — subprocess owns it

    # -- interface -----------------------------------------------------------
    def build_url(self, query: str, location: str) -> str:
        raise NotImplementedError

    def parse(self, html: str, max_results: int) -> list[dict]:
        raise NotImplementedError

    def _browse(self, url: str) -> dict:
        """Run Playwright in a subprocess to avoid asyncio-loop conflict."""
        script_path = os.path.join(os.path.dirname(__file__), "_browse_runner.py")
        # Write the runner script
        with open(script_path, "w") as f:
            f.write(_BROWSE_SCRIPT)
        try:
            proc = subprocess.run(
                [sys.executable, script_path, url, self.wait_selector, str(self.min_delay)],
                capture_output=True, text=True, timeout=45
            )
            if proc.returncode != 0:
                logger.warning("%s: subprocess error: %s", self.name, proc.stderr[:200])
                return {"status": "ERROR", "html": ""}
            return json.loads(proc.stdout.strip().split("\n")[-1])
        except subprocess.TimeoutExpired:
            logger.warning("%s: browser subprocess timed out", self.name)
            return {"status": "ERROR", "html": ""}
        except Exception as e:
            logger.warning("%s: browser subprocess error: %s", self.name, e)
            return {"status": "ERROR", "html": ""}

    def search(self, query: str, location: str = "", max_results: int = 10) -> list[dict]:
        if not self.available:
            logger.warning("%s: Playwright not installed — scraper UNAVAILABLE. "
                           "pip install playwright && playwright install chromium",
                           self.name)
            return []
        if self.blocked:
            return []
        try:
            url = self.build_url(query, location)
            result = self._browse(url)
            status = result.get("status", "ERROR")
            html = result.get("html", "")
            if status == "BLOCKED":
                self.blocked = True
                logger.error("%s: block/CAPTCHA page detected — marked BLOCKED.", self.name)
                return []
            if status == "SELECTOR_MISS":
                logger.warning("%s: SELECTOR MISS — page loaded but '%s' never appeared.",
                               self.name, self.wait_selector)
                return []
            if status == "ERROR":
                logger.warning("%s: browser error: %s", self.name, result.get("error", ""))
                return []
            jobs = self.parse(html, max_results)
            if not jobs:
                logger.warning("%s: SELECTOR MISS — 0 cards parsed. Update selectors.",
                               self.name)
            return jobs
        except Exception as e:
            logger.warning("%s: search error: %s", self.name, e)
            return []


def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml")


class NaukriScraper(BrowserScraper):
    name = "naukri"
    wait_selector = "div.srp-jobtuple-wrapper, article.jobTuple"

    def build_url(self, query, location):
        q = query.strip().lower().replace(" ", "-")
        loc = (location or "").strip().lower().replace(" ", "-")
        return (f"https://www.naukri.com/{q}-jobs-in-{loc}"
                if loc else f"https://www.naukri.com/{q}-jobs")

    def parse(self, html, max_results):
        jobs = []
        for card in _soup(html).select(
                "div.srp-jobtuple-wrapper, article.jobTuple")[:max_results]:
            a = card.select_one("a.title, a.jobTitle")
            if not a or not a.get("href"):
                continue
            jobs.append({
                "title": clean_text(a),
                "company": clean_text(card.select_one("a.comp-name, a.subTitle")),
                "location": clean_text(card.select_one("span.locWdth, .location")),
                "salary": clean_text(card.select_one("span.sal-wrap, .salary"))
                          or parse_salary(clean_text(card)),
                "url": a["href"].split("?")[0],
                "posted_days": parse_posted_days(
                    clean_text(card.select_one("span.job-post-day, .postedDate"))),
                "description": clean_text(card.select_one("span.job-desc, .job-description")),
                "source": "Naukri",
            })
        return jobs


class IndeedScraper(BrowserScraper):
    name = "indeed"
    wait_selector = "div.job_seen_beacon"

    def build_url(self, query, location):
        from urllib.parse import quote_plus
        return (f"https://in.indeed.com/jobs?q={quote_plus(query)}"
                f"&l={quote_plus(location or '')}&fromage=7")

    def parse(self, html, max_results):
        jobs = []
        for card in _soup(html).select("div.job_seen_beacon")[:max_results]:
            a = card.select_one("h2.jobTitle a, a.jcs-JobTitle")
            if not a:
                continue
            href = a.get("href", "")
            if href.startswith("/"):
                href = "https://in.indeed.com" + href
            jobs.append({
                "title": clean_text(a),
                "company": clean_text(card.select_one(
                    "[data-testid='company-name'], span.companyName")),
                "location": clean_text(card.select_one(
                    "[data-testid='text-location'], div.companyLocation")),
                "salary": clean_text(card.select_one(
                    ".salary-snippet-container, [data-testid='attribute_snippet_testid']"))
                          or parse_salary(clean_text(card)),
                "url": href.split("&")[0],
                "posted_days": parse_posted_days(clean_text(card.select_one(
                    "[data-testid='myJobsStateDate'], span.date"))),
                "description": clean_text(card.select_one(
                    "div.job-snippet, [data-testid='belowJobSnippet']")),
                "source": "Indeed",
            })
        return jobs


class ShineScraper(BrowserScraper):
    name = "shine"
    wait_selector = "div[class*='jobCard'], div.search_listing"

    def build_url(self, query, location):
        q = query.strip().lower().replace(" ", "-")
        loc = (location or "").strip().lower().replace(" ", "-")
        return (f"https://www.shine.com/job-search/{q}-jobs-in-{loc}"
                if loc else f"https://www.shine.com/job-search/{q}-jobs")

    def parse(self, html, max_results):
        jobs = []
        for card in _soup(html).select(
                "div[class*='jobCard'], div.search_listing div[class*='result']")[:max_results]:
            a = card.select_one("a[href*='-jd'], h2 a, a[class*='title']")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.shine.com" + href
            jobs.append({
                "title": clean_text(a),
                "company": clean_text(card.select_one(
                    "[class*='company'], span[class*='Comp']")),
                "location": clean_text(card.select_one("[class*='location']")),
                "salary": parse_salary(clean_text(card)),
                "url": href.split("?")[0],
                "posted_days": parse_posted_days(clean_text(card)),
                "description": "",
                "source": "Shine",
            })
        return jobs


class FounditScraper(BrowserScraper):
    name = "foundit"
    wait_selector = "div.srpResultCardContainer, div[class*='cardContainer']"

    def build_url(self, query, location):
        from urllib.parse import quote_plus
        return (f"https://www.foundit.in/srp/results?query={quote_plus(query)}"
                f"&locations={quote_plus(location or '')}")

    def parse(self, html, max_results):
        jobs = []
        for card in _soup(html).select(
                "div.srpResultCardContainer, div[class*='cardContainer']")[:max_results]:
            a = card.select_one("a[href*='/job/'], h3 a, div.jobTitle a")
            title_node = a or card.select_one("h3, div.jobTitle")
            if not title_node:
                continue
            href = a["href"] if a and a.get("href") else ""
            if href.startswith("/"):
                href = "https://www.foundit.in" + href
            jobs.append({
                "title": clean_text(title_node),
                "company": clean_text(card.select_one(
                    "span.companyName, div.companyName, [class*='company']")),
                "location": clean_text(card.select_one("[class*='location'], .details")),
                "salary": parse_salary(clean_text(card)),
                "url": href.split("?")[0],
                "posted_days": parse_posted_days(clean_text(card)),
                "description": "",
                "source": "Foundit",
            })
        return jobs


class GlassdoorScraper(BrowserScraper):
    name = "glassdoor"
    wait_selector = "li[data-test='jobListing'], ul[aria-label='Jobs List'] li"

    def build_url(self, query, location):
        from urllib.parse import quote_plus
        return (f"https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword={quote_plus(query)}"
                f"&locKeyword={quote_plus(location or '')}")

    def parse(self, html, max_results):
        jobs = []
        for card in _soup(html).select("li[data-test='jobListing']")[:max_results]:
            a = card.select_one("a[data-test='job-title'], a[href*='/job-listing/']")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.glassdoor.co.in" + href
            jobs.append({
                "title": clean_text(a),
                "company": clean_text(card.select_one(
                    "[class*='EmployerProfile'], span[class*='employer']")),
                "location": clean_text(card.select_one("[data-test='emp-location']")),
                "salary": clean_text(card.select_one("[data-test='detailSalary']"))
                          or parse_salary(clean_text(card)),
                "url": href.split("?")[0],
                "posted_days": parse_posted_days(
                    clean_text(card.select_one("[data-test='job-age']"))),
                "description": "",
                "source": "Glassdoor",
            })
        return jobs
