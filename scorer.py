"""
Scorer v2 - Match scores between jobs and CV profile.

Fixes over v1:
  1. Rescaling: components are only scored on data that EXISTS. v1 scored
     skill-match (40 pts) and keyword-match (20 pts) against the description;
     when description was "N/A" both collapsed toward 0 and every job capped
     near ~50 ("Moderate"). v2 redistributes weight to available fields, and
     records which fields were used.
  2. Word-boundary matching: v1 used substring `in` — "r" matched everything,
     "ml" matched "html", "ai" matched "chain".
  3. Capped skill denominator: ratio is against min(len(skills), 15) matched,
     not against a 50-item bloated skill list.
  4. No free location points: v1 gave 10 pts to any Bengaluru job even if the
     CV said Mumbai.

Each scored job gets: score (0-100), score_basis ("title-only" | "full-text"),
matched_skills (list).
"""

import re
from difflib import SequenceMatcher

# Generic words that don't discriminate between roles
STOPWORDS = {"analyst", "senior", "junior", "associate", "specialist", "jobs",
             "job", "the", "and", "of", "in", "for", "a", "an"}

INDIA_CITIES = ["mumbai", "delhi", "pune", "hyderabad", "chennai",
                "gurgaon", "noida", "gurugram", "kolkata", "ahmedabad", "india"]


def _word_in(term: str, text: str) -> bool:
    """Whole-word / whole-phrase match, case-insensitive."""
    if not term or not text:
        return False
    return re.search(r"(?<![\w])" + re.escape(term.lower()) + r"(?![\w])", text) is not None


def _title_component(cv_roles: list[str], job_title: str) -> float:
    """0..1 : how well the title matches any suggested role."""
    best = 0.0
    for role in cv_roles:
        role_clean = role.lower().replace("/", " ")
        if role_clean in job_title:
            return 1.0
        ratio = SequenceMatcher(None, role_clean, job_title).ratio()
        best = max(best, ratio if ratio > 0.5 else 0)
        role_words = {w for w in role_clean.split() if w not in STOPWORDS}
        title_words = {w for w in job_title.split() if w not in STOPWORDS}
        if role_words:
            best = max(best, len(role_words & title_words) / len(role_words) * 0.85)
    return min(best, 1.0)


def _skill_component(cv_skills: list[str], text: str) -> tuple[float, list[str]]:
    """0..1 + matched skill list. Denominator capped at 15."""
    if not cv_skills:
        return 0.25, []
    matched = [s for s in cv_skills if _word_in(s, text)]
    denom = min(len(cv_skills), 15)
    return min(len(matched) / denom, 1.0), matched


def _keyword_component(text: str) -> float:
    """0..1 : breadth of domain-category coverage in job text."""
    cats = {
        "finance": ["finance", "financial", "investment", "portfolio", "equity",
                    "fund", "credit", "risk", "compliance", "audit", "banking", "asset"],
        "tech": ["python", "sql", "data", "analytics", "excel", "power bi",
                 "tableau", "machine learning", "api", "automation", "pipeline"],
        "writing": ["writing", "proposal", "rfp", "ddq", "content",
                    "documentation", "report"],
        "analysis": ["analysis", "research", "valuation", "modeling", "forecast"],
    }
    hit = sum(1 for kws in cats.values() if any(_word_in(k, text) for k in kws))
    return hit / len(cats)


def _location_component(cv_loc: str, job_loc: str) -> float:
    """0..1. No unconditional home-city bonus."""
    if not job_loc:
        return 0.3
    if "remote" in job_loc:
        return 0.8
    if not cv_loc:
        return 0.3
    # Treat bangalore/bengaluru as same city
    norm = lambda s: s.replace("bangalore", "bengaluru")
    cv_n, job_n = norm(cv_loc), norm(job_loc)
    if cv_n in job_n or job_n in cv_n:
        return 1.0
    if any(c in job_n for c in INDIA_CITIES):
        return 0.4
    return 0.0


def _experience_component(text: str) -> float:
    """0..1 heuristic on years-of-experience mention."""
    years = [int(y) for y in re.findall(r"(\d+)\+?\s*(?:years?|yrs?)", text)]
    if not years:
        return 0.6
    if any(y <= 3 for y in years):
        return 0.8
    if any(3 <= y <= 7 for y in years):
        return 1.0
    return 0.3


def calculate_match_score(cv_data: dict, job: dict) -> float:
    """Score 0-100. Also sets job['score_basis'] and job['matched_skills']."""
    job_title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").strip()
    has_desc = bool(desc) and desc.upper() != "N/A" and len(desc) >= 60
    job_text = f"{job_title} {desc.lower()}" if has_desc else job_title

    cv_skills = [s.lower() for s in cv_data.get("skills", [])]
    cv_roles = [r.lower() for r in cv_data.get("suggested_roles", [])]
    cv_loc = (cv_data.get("location") or "").lower()
    job_loc = (job.get("location") or "").lower()

    t = _title_component(cv_roles, job_title)
    s, matched = _skill_component(cv_skills, job_text)
    k = _keyword_component(job_text)
    l = _location_component(cv_loc, job_loc)
    e = _experience_component(job_text)

    if has_desc:
        # weights: title 25, skills 35, keywords 15, location 15, exp 10
        score = t * 25 + s * 35 + k * 15 + l * 15 + e * 10
        job["score_basis"] = "full-text"
    else:
        # No description → don't pretend to measure skill depth from a title.
        # weights: title 55, skills(title-only) 15, location 20, exp 10
        score = t * 55 + s * 15 + l * 20 + e * 10
        job["score_basis"] = "title-only"

    job["matched_skills"] = matched
    # Skills gap: what the JOB text mentions from a broad skill vocab that CV lacks
    job["missing_skills"] = _skills_gap(cv_skills, job_text) if has_desc else []
    return round(min(score, 100), 1)


# Broad vocab for gap detection (job-side requirements)
GAP_VOCAB = ["python", "sql", "excel", "power bi", "tableau", "r programming",
             "vba", "sap", "oracle", "bloomberg", "financial modeling", "dcf",
             "valuation", "equity research", "aml", "kyc", "compliance",
             "machine learning", "etl", "data analysis", "alteryx", "salesforce"]


def _skills_gap(cv_skills: list[str], job_text: str) -> list[str]:
    """Skills the job mentions that the CV does not have."""
    cv_set = set(cv_skills)
    return [s for s in GAP_VOCAB
            if s not in cv_set and _word_in(s, job_text)]


def rank_jobs(cv_data: dict, jobs: list[dict]) -> list[dict]:
    """Score and rank jobs; highest first."""
    for job in jobs:
        job["score"] = calculate_match_score(cv_data, job)
    jobs.sort(key=lambda j: j["score"], reverse=True)
    return jobs


def get_match_label(score: float) -> str:
    if score >= 80:
        return "🟢 Excellent Match"
    elif score >= 60:
        return "🔵 Good Match"
    elif score >= 40:
        return "🟡 Moderate Match"
    elif score >= 20:
        return "🟠 Low Match"
    return "🔴 Poor Match"
