"""
Checker - Maker-Checker QC gate for LITSEARCH.

The scrapers are the MAKER. This module is the CHECKER.
Every scraped record must pass validation BEFORE it is scored or exported.

Rejects:
  R1  SERP/listing-page URL (link to a search page, not a job posting)
  R2  Aggregate title ("15,000+ Data Analyst jobs", "Compliance Job Vacancies")
  R3  Missing/empty title
  R4  Duplicate canonical URL

Flags (kept, but marked and confidence-reduced):
  F1  Missing company
  F2  Missing/short description  (scoring must rescale, not silently zero out)
  F3  Missing salary/location    (informational)

Also produces a portal health report: any portal that returned 0 results is
surfaced as DEAD instead of being silently hidden in a summary row.
"""

import re
from urllib.parse import urlparse, urlunparse


# --- URL patterns that identify a REAL job-detail page, per portal ---
JOB_DETAIL_PATTERNS = [
    r"linkedin\.com/jobs/view/",
    r"indeed\.com/(viewjob|rc/clk|m/viewjob)",
    r"naukri\.com/job-listings-",
    r"foundit\.in/(job|jobs)/[^/]+-\d+",
    r"shine\.com/jobs/.+-jd",
    r"glassdoor\.(com|co\.in)/job-listing/",
    r"monster\.com/job-openings/",
    r"timesjobs\.com/job-detail",
]

# --- URL patterns that identify a LISTING/SERP page (never a job) ---
LISTING_URL_PATTERNS = [
    r"linkedin\.com/jobs/[a-z0-9-]+-jobs(-[a-z-]+)?/?$",     # /jobs/data-analyst-jobs-bengaluru
    r"naukri\.com/[a-z0-9-]+-jobs-in-[a-z-]+/?$",
    r"indeed\.com/q-.+-jobs\.html",
    r"foundit\.in/search/",
    r"glassdoor\.[a-z.]+/Job/",
    r"shine\.com/job-search/",
    r"duckduckgo\.com|google\.com/search|bing\.com/search",
]

# --- Titles that are aggregates/counts, not postings ---
AGGREGATE_TITLE_PATTERNS = [
    r"^\s*[\d,]+\+?\s",                       # "15,000+ Data Analyst..."
    r"\b[\d,]{3,}\+?\s*(jobs?|vacanc)",       # "1,429 data analyst jobs"
    r"\b(jobs?|vacancies|openings?)\s*(in\b|$)",  # ends "...jobs" / "...jobs in X"
    r"(?i)\bjob\s+vacancies\b",
    r"(?i)^top\s+\d+",
    r"(?i)\bhiring\s+now\b$",
]


def canonical_url(url: str) -> str:
    """Strip tracking query params + fragment so dedup works across refIds."""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        path = p.path.rstrip("/")
        return urlunparse((p.scheme or "https", p.netloc.lower(), path, "", "", ""))
    except Exception:
        return url.strip().lower()


def is_job_detail_url(url: str) -> bool:
    u = (url or "").lower()
    return any(re.search(pat, u) for pat in JOB_DETAIL_PATTERNS)


def is_listing_url(url: str) -> bool:
    u = (url or "").lower()
    return any(re.search(pat, u) for pat in LISTING_URL_PATTERNS)


def is_aggregate_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return any(re.search(pat, t, re.IGNORECASE) for pat in AGGREGATE_TITLE_PATTERNS)


def check_job(job: dict) -> dict:
    """
    Validate one scraped record.

    Returns:
        {"status": "ACCEPT"|"REJECT", "rejects": [...], "flags": [...],
         "confidence": "HIGH"|"MEDIUM"|"LOW"}
    """
    rejects, flags = [], []
    title = (job.get("title") or "").strip()
    url = (job.get("url") or "").strip()
    company = (job.get("company") or "").strip()
    desc = (job.get("description") or "").strip()

    # --- Hard rejects ---
    if not title:
        rejects.append("R3:empty-title")
    if is_aggregate_title(title):
        rejects.append("R2:aggregate-title")
    if url:
        if is_listing_url(url):
            rejects.append("R1:listing-url")
        elif not is_job_detail_url(url):
            # Unknown portal URL shape: don't reject outright, but flag hard.
            flags.append("F0:unverified-url")
    else:
        rejects.append("R1:no-url")

    # --- Soft flags ---
    if not company:
        flags.append("F1:no-company")
    if not desc or desc.upper() == "N/A" or len(desc) < 60:
        flags.append("F2:no-description")
    if not (job.get("salary") or "").strip():
        flags.append("F3:no-salary")
    if not (job.get("location") or "").strip():
        flags.append("F3:no-location")

    status = "REJECT" if rejects else "ACCEPT"
    hard_flags = sum(1 for f in flags if f.startswith(("F0", "F1", "F2")))
    confidence = "HIGH" if hard_flags == 0 else ("MEDIUM" if hard_flags == 1 else "LOW")

    return {"status": status, "rejects": rejects, "flags": flags, "confidence": confidence}


def run_checker(jobs: list[dict], portal_counts: dict = None) -> dict:
    """
    Run the full maker-checker pass over scraped jobs.

    Mutates accepted jobs in place: adds 'qc_flags', 'qc_confidence',
    'canonical_url'. Rejected jobs get 'qc_reasons'.

    Returns:
        {
          "accepted": [...], "rejected": [...],
          "reject_reasons": {reason: count},
          "flag_counts": {flag: count},
          "dead_portals": [...], "portal_counts": {...},
        }
    """
    accepted, rejected = [], []
    reject_reasons, flag_counts = {}, {}
    seen_urls = set()

    for job in jobs:
        result = check_job(job)
        cu = canonical_url(job.get("url", ""))
        job["canonical_url"] = cu

        if result["status"] == "ACCEPT" and cu:
            if cu in seen_urls:
                result["status"] = "REJECT"
                result["rejects"].append("R4:duplicate-url")
            else:
                seen_urls.add(cu)

        if result["status"] == "REJECT":
            job["qc_reasons"] = result["rejects"]
            rejected.append(job)
            for r in result["rejects"]:
                reject_reasons[r] = reject_reasons.get(r, 0) + 1
        else:
            job["qc_flags"] = result["flags"]
            job["qc_confidence"] = result["confidence"]
            accepted.append(job)
            for f in result["flags"]:
                flag_counts[f] = flag_counts.get(f, 0) + 1

    dead_portals = sorted(
        p for p, c in (portal_counts or {}).items() if int(c) == 0
    )

    return {
        "accepted": accepted,
        "rejected": rejected,
        "reject_reasons": reject_reasons,
        "flag_counts": flag_counts,
        "dead_portals": dead_portals,
        "portal_counts": portal_counts or {},
    }


def format_checker_summary(report: dict) -> str:
    """Plain-text summary for CLI output."""
    lines = []
    n_acc, n_rej = len(report["accepted"]), len(report["rejected"])
    lines.append(f"CHECKER: {n_acc} accepted / {n_rej} rejected "
                 f"of {n_acc + n_rej} scraped records")
    if report["reject_reasons"]:
        lines.append("  Reject reasons: " + ", ".join(
            f"{k}={v}" for k, v in sorted(report["reject_reasons"].items())))
    if report["flag_counts"]:
        lines.append("  Flags on accepted: " + ", ".join(
            f"{k}={v}" for k, v in sorted(report["flag_counts"].items())))
    if report["dead_portals"]:
        lines.append("  ⚠ DEAD PORTALS (0 results — scraper broken or blocked): "
                     + ", ".join(report["dead_portals"]))
    return "\n".join(lines)
