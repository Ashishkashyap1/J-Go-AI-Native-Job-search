"""
Keyword Analyzer - Generates optimized search queries from CV data.
"""

import re
from itertools import combinations


# Synonyms for broadening search
SKILL_SYNONYMS = {
    "equity research": ["stock research", "share research", "investment research", "market research finance"],
    "valuation": ["company valuation", "business valuation", "financial valuation"],
    "financial statement analysis": ["financial analysis", "fundamental analysis", "accounting analysis"],
    "proposal writing": ["rfp response", "bid writing", "tender writing", "business proposal"],
    "due diligence": ["dd process", "risk assessment", "counterparty review"],
    "data analysis": ["data analytics", "business intelligence", "data mining"],
    "python": ["python programming", "python developer", "python scripting"],
    "seo": ["search engine optimization", "digital marketing", "content strategy"],
    "product design": ["product development", "ux design", "ui/ux"],
    "aml": ["anti money laundering", "financial crime", "regulatory compliance"],
    "kyc": ["know your customer", "client onboarding", "customer verification"],
    "bloomberg": ["bloomberg terminal", "financial data terminal", "market data"],
    "portfolio management": ["investment portfolio", "fund management", "asset allocation"],
    "credit analysis": ["credit risk", "lending analysis", "credit assessment"],
    "compliance": ["regulatory compliance", "policy compliance", "audit compliance"],
    "content writing": ["content creation", "copywriting", "editorial"],
    "technical writing": ["technical documentation", "technical author", "documentation specialist"],
    "risk management": ["risk assessment", "risk analysis", "enterprise risk"],
    "financial modeling": ["financial model", "valuation model", "forecasting model"],
    "power bi": ["powerbi", "microsoft power bi", "business intelligence dashboard"],
}

# Experience level mappings
EXPERIENCE_KEYWORDS = {
    "entry": ["junior", "associate", "trainee", "intern", "fresher", "entry level", "graduate"],
    "mid": ["analyst", "specialist", "consultant", "developer", "engineer", "officer", "2+ years", "3+ years"],
    "senior": ["senior", "lead", "principal", "manager", "director", "head", "vp", "5+ years", "8+ years"],
}


def generate_search_queries(cv_data: dict, max_queries: int = 25) -> list[dict]:
    """
    Generate optimized search queries from CV data.

    Returns a list of dicts: {"query": str, "source_skills": list[str], "priority": int}
    Priority 1 = highest relevance
    """
    queries = []
    skills = [s.lower() for s in cv_data.get("skills", [])]
    roles = [r.lower() for r in cv_data.get("suggested_roles", [])]
    location = cv_data.get("location", "").lower()

    # --- Priority 1: Direct role-based queries ---
    for role in roles:
        base_role = re.sub(r"\s*/\s.*", "", role)  # Take first part of slash-separated roles
        query = base_role
        if location:
            query += f" {location}"
        queries.append({
            "query": query,
            "source_skills": [role],
            "priority": 1,
        })

    # --- Priority 2: Skill + role combinations ---
    role_keywords = ["analyst", "developer", "specialist", "consultant", "writer", "manager"]
    top_skills = skills[:10]  # Focus on top 10 skills

    for skill in top_skills:
        for role_kw in role_keywords:
            if role_kw in skill or any(rw in skill for rw in role_keywords):
                continue  # Skip if skill already contains role keyword
            query = f"{skill} {role_kw}"
            if location:
                query += f" {location}"
            queries.append({
                "query": query,
                "source_skills": [skill],
                "priority": 2,
            })

    # --- Priority 3: Synonym-expanded queries ---
    for skill in top_skills:
        synonyms = SKILL_SYNONYMS.get(skill, [])
        for syn in synonyms[:2]:  # Limit to 2 synonyms per skill
            query = syn
            if location:
                query += f" {location}"
            queries.append({
                "query": query,
                "source_skills": [skill, syn],
                "priority": 3,
            })

    # --- Priority 4: Skill pair combinations (for cross-functional roles) ---
    if len(top_skills) >= 2:
        for s1, s2 in combinations(top_skills[:6], 2):
            # Skip if both are very similar
            if s1 in s2 or s2 in s1:
                continue
            query = f"{s1} {s2}"
            if location:
                query += f" {location}"
            queries.append({
                "query": query,
                "source_skills": [s1, s2],
                "priority": 4,
            })

    # Deduplicate and limit
    seen = set()
    unique_queries = []
    for q in queries:
        key = q["query"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_queries.append(q)

    # Sort by priority and return top N
    unique_queries.sort(key=lambda x: x["priority"])
    return unique_queries[:max_queries]


def extract_search_terms_from_job(title: str, description: str = "") -> list[str]:
    """Extract key terms from a job listing for matching."""
    text = f"{title} {description}".lower()
    terms = set()

    # Extract skill mentions
    all_skills = []
    for category_skills in [
        SKILL_SYNONYMS.keys(),
        *[v for v in SKILL_SYNONYMS.values()],
    ]:
        all_skills.extend(category_skills)

    for skill in all_skills:
        if skill.lower() in text:
            terms.add(skill.lower())

    # Extract role-related terms
    role_terms = re.findall(
        r"(?i)\b(analyst|developer|engineer|manager|specialist|consultant|writer|designer|architect|lead|director|associate|intern|trainee)\b",
        text,
    )
    terms.update([t.lower() for t in role_terms])

    return sorted(terms)
