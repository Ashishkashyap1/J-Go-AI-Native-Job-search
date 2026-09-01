"""
CV Parser - Extracts skills, experience, keywords from PDF resumes.
"""

import json
import os
import re
from pathlib import Path

try:
    import pymupdf
except ImportError:
    pymupdf = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None


# --- Comprehensive skill & keyword patterns ---
SKILL_PATTERNS = {
    "programming": [
        "python", "r", "sql", "javascript", "nodejs", "node.js", "react", "astro",
        "html", "css", "tailwind", "tailwind css", "excel", "vba", "matlab",
    ],
    "finance": [
        "equity research", "valuation", "dcf", "financial modeling", "financial statement analysis",
        "portfolio management", "risk management", "derivatives", "fixed income", "credit analysis",
        "aml", "kyc", "compliance", "due diligence", "rfp", "ddq", "aif", "mutual fund",
        "bloomberg terminal", "alteryx", "fund of funds", "alternatives", "private credit",
        "pre-ipo", "rhp", "drhp", "nav", "cfa", "nism", "sebi",
    ],
    "data_analytics": [
        "data analysis", "data engineering", "data pipeline", "etl", "powerbi", "power bi",
        "tableau", "data visualization", "machine learning", "ml", "ai", "artificial intelligence",
        "pandas", "numpy", "scipy", "data science", "analytics",
    ],
    "writing": [
        "proposal writing", "technical writing", "proofreading", "proof-reading",
        "content writing", "copywriting", "report writing", "grant writing",
        "rfp response", "ddq response",
    ],
    "tools": [
        "bloomberg", "qvidian", "dealcloud", "crm", "salesforce",
        "ms excel", "google sheets", "powerpoint", "ms word",
        "jira", "confluence", "notion", "slack", "github", "git",
    ],
    "product": [
        "product management", "product design", "seo", "ux", "ui",
        "figma", "sketch", "adobe xd", "wireframing", "prototyping",
    ],
    "domain": [
        "fintech", "banking", "investment banking", "wealth management",
        "asset management", "insurance", "consulting", "audit",
        "tax", "accounting", "commerce", "marketing",
    ],
}

# Role title patterns — includes fresher / early-career variants
ROLE_PATTERNS = [
    # --- Finance (fresher-friendly) ---
    (r"(?i)\b(junior\s+equity\s+research|equity\s+research\s+analyst|research\s+analyst)\b", "Equity Research Analyst"),
    (r"(?i)\b(junior\s+financial\s+analyst|graduate\s+finance|financial\s+analyst|finance\s+analyst)\b", "Financial Analyst"),
    (r"(?i)\b(junior\s+data\s+analyst|data\s+analyst)\b", "Data Analyst"),
    (r"(?i)\b(junior\s+business\s+analyst|business\s+analyst)\b", "Business Analyst"),
    (r"(?i)\b(quantitative\s+analyst|quant\s+analyst|quant)\b", "Quantitative Analyst"),
    (r"(?i)\b(portfolio\s+analyst|portfolio\s+manager)\b", "Portfolio Analyst"),
    (r"(?i)\b(risk\s+analyst|risk\s+manager)\b", "Risk Analyst"),
    (r"(?i)\b(junior\s+compliance|compliance\s+analyst|compliance\s+officer)\b", "Compliance Analyst"),
    (r"(?i)\b(junior\s+credit\s+analyst|credit\s+analyst)\b", "Credit Analyst"),
    (r"(?i)\b(investment\s+analyst|investment\s+banking\s+analyst)\b", "Investment Analyst"),
    (r"(?i)\b(junior\s+aml|aml\s+analyst|junior\s+kyc|kyc\s+analyst)\b", "AML/KYC Analyst"),
    (r"(?i)\b(due\s+diligence\s+analyst)\b", "Due Diligence Analyst"),
    (r"(?i)\b(fintech\s+analyst)\b", "FinTech Analyst"),
    # --- Writing / RFP (fresher-friendly) ---
    (r"(?i)\b(proposal\s+writer|rfp\s+specialist|rfp\s+writer)\b", "Proposal Writer"),
    (r"(?i)\b(technical\s+writer)\b", "Technical Writer"),
    (r"(?i)\b(content\s+writer|copywriter)\b", "Content Writer"),
    # --- Product / Design (fresher-friendly) ---
    (r"(?i)\b(junior\s+product\s+designer|product\s+designer|ui/ux\s+designer)\b", "Product Designer"),
    (r"(?i)\b(product\s+manager|pm)\b", "Product Manager"),
    (r"(?i)\b(product\s+analyst)\b", "Product Analyst"),
    # --- Tech (fresher-friendly) ---
    (r"(?i)\b(junior\s+data\s+engineer|data\s+engineer)\b", "Data Engineer"),
    (r"(?i)\b(junior\s+python\s+developer|python\s+developer|software\s+engineer)\b", "Python Developer"),
    (r"(?i)\b(seo\s+specialist|seo\s+analyst|junior\s+seo)\b", "SEO Specialist"),
    # --- Fresher / Intern / Trainee catch-all ---
    (r"(?i)\b(finance\s+trainee|finance\s+intern|accounting\s+trainee)\b", "Finance Trainee"),
    (r"(?i)\b(banking\s+trainee|banking\s+intern|credit\s+trainee)\b", "Banking Trainee"),
    (r"(?i)\b(data\s+analytics\s+intern|analytics\s+intern)\b", "Data Analytics Intern"),
    (r"(?i)\b(compliance\s+intern|risk\s+intern|audit\s+intern)\b", "Compliance Intern"),
    (r"(?i)\b(investment\s+intern|wealth\s+management\s+intern)\b", "Investment Intern"),
    (r"(?i)\b(marketing\s+intern|digital\s+marketing\s+intern|content\s+intern)\b", "Marketing Intern"),
    (r"(?i)\b(product\s+intern|design\s+intern|ux\s+intern)\b", "Product Intern"),
]


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file using pymupdf or PyPDF2."""
    text = ""

    if pymupdf:
        try:
            doc = pymupdf.open(pdf_path)
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
            if text.strip():
                return text
        except Exception:
            pass

    if PyPDF2:
        try:
            reader = PyPDF2.PdfReader(pdf_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            if text.strip():
                return text
        except Exception:
            pass

    # Fallback: try reading as plain text
    try:
        with open(pdf_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        pass

    return text


# Tokens too ambiguous to trust as bare words on a CV
AMBIGUOUS_SKILLS = {"r", "ai", "ml", "ba", "pm", "ca"}


def extract_skills(text: str) -> list[str]:
    """Extract technical skills from CV text (whole-word/phrase match only).

    v1 used substring `in`: "r" matched every word containing the letter r,
    "ml" matched "html", "ai" matched "chain" — the skill list ballooned and
    wrecked the scorer's skill-ratio denominator.
    """
    found = set()
    text_lower = text.lower()
    for category, skills in SKILL_PATTERNS.items():
        for skill in skills:
            s = skill.lower()
            if s in AMBIGUOUS_SKILLS:
                continue  # only accept via explicit context elsewhere
            if re.search(r"(?<![\w])" + re.escape(s) + r"(?![\w])", text_lower):
                found.add(skill)
    # Ambiguous single/double-letter skills need contextual evidence
    if re.search(r"(?<![\w])r(?![\w])\s*(programming|language|studio)", text_lower):
        found.add("r")
    if re.search(r"machine\s+learning", text_lower):
        found.add("machine learning")
    return sorted(found)


def extract_experience(text: str) -> list[dict]:
    """Extract work experience entries from CV text."""
    experiences = []
    lines = text.split("\n")

    # Common company names to look for
    company_keywords = [
        "goldman sachs", "morgan stanley", "jp morgan", "hdfc", "icici", "axis",
        "infosys", "tcs", "wipro", "accenture", "deloitte", "pwc", "kpmg",
        "ey", "bain", "mckinsey", "bcg", "first assetz", "knowledge bell",
    ]

    current_exp = None
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        line_lower = line_stripped.lower()
        # Skip bullet/continuation lines — they are responsibilities, not headers
        if line_stripped.startswith(("•", "-", "*", "\u2022")):
            pass
        else:
            for company in company_keywords:
                # company name must appear in first 60 chars of a header-ish line
                if company in line_lower[:60] and len(line_stripped) < 90:
                    if current_exp:
                        experiences.append(current_exp)
                    current_exp = {"company": line_stripped, "role": "", "duration": ""}
                    break

        if current_exp and not current_exp["role"]:
            # Look for role/title patterns
            role_match = re.search(
                r"(?i)(analyst|trainee|intern|manager|director|associate|engineer|specialist|coordinator|consultant|officer|lead|head|vp|vice president|senior|junior)",
                line_stripped,
            )
            if role_match:
                current_exp["role"] = line_stripped

        if current_exp and not current_exp["duration"]:
            date_match = re.search(
                r"(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4}\s*[-–—]\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4}|present|\d{4}\s*[-–—]\s*\d{4}",
                line_stripped,
            )
            if date_match:
                current_exp["duration"] = date_match.group()

    if current_exp:
        experiences.append(current_exp)

    return experiences


def extract_education(text: str) -> list[str]:
    """Extract education information from CV text."""
    education = []
    edu_keywords = ["bachelor", "master", "mba", "b.com", "b.sc", "b.tech", "m.com", "m.sc",
                     "m.tech", "phd", "ca", "cfa", "degree", "diploma", "university", "college"]

    lines = text.split("\n")
    for line in lines:
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in edu_keywords):
            education.append(line.strip())

    return education


def extract_certifications(text: str) -> list[str]:
    """Extract certifications from CV text."""
    certs = []
    cert_keywords = [
        "cfa", "nism", "ca", "cpa", "frm", "series 7", "series 63", "series 66",
        "aws", "azure", "google cloud", "pmp", "six sigma", "certified",
        "ncce", "ncc", "cadet corps",
    ]

    text_lower = text.lower()
    lines = text.split("\n")
    for line in lines:
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in cert_keywords):
            certs.append(line.strip())

    return certs


def extract_roles_from_cv(text: str) -> list[str]:
    """Infer potential job roles from CV content -- includes fresher / early-career roles."""
    roles = set()
    text_lower = text.lower()

    for pattern, role_title in ROLE_PATTERNS:
        if re.search(pattern, text):
            roles.add(role_title)

    # --- Skill-based role inference (fresher-friendly) ---
    # Finance
    if "equity" in text_lower and "research" in text_lower:
        roles.add("Junior Equity Research Analyst")
    if "financial" in text_lower and ("analys" in text_lower or "model" in text_lower):
        roles.add("Junior Financial Analyst")
    if "due diligence" in text_lower:
        roles.add("Due Diligence Analyst")
    if "compliance" in text_lower or "aml" in text_lower or "kyc" in text_lower:
        roles.add("Junior Compliance Analyst")
    if "credit" in text_lower or "lending" in text_lower:
        roles.add("Credit Analyst")
    if "portfolio" in text_lower or "mutual fund" in text_lower or "aif" in text_lower:
        roles.add("Fund Operations Trainee")
    if "bloomberg" in text_lower or "valuation" in text_lower or "dcf" in text_lower:
        roles.add("Finance Analyst")
    if "audit" in text_lower or "accounting" in text_lower:
        roles.add("Audit / Accounts Trainee")
    # Data / Tech
    if "python" in text_lower and "data" in text_lower:
        roles.add("Junior Data Analyst")
    if "sql" in text_lower and ("data" in text_lower or "analys" in text_lower):
        roles.add("Data Analyst")
    if "data" in text_lower and ("pipeline" in text_lower or "engineering" in text_lower or "etl" in text_lower):
        roles.add("Junior Data Engineer")
    # Writing
    if "proposal" in text_lower and ("write" in text_lower or "writing" in text_lower):
        roles.add("Junior Proposal Writer")
    if "technical" in text_lower and "writing" in text_lower:
        roles.add("Technical Writer")
    if "content" in text_lower and ("write" in text_lower or "writing" in text_lower):
        roles.add("Content Writer")
    # Product / Design / SEO
    if "seo" in text_lower:
        roles.add("Junior SEO Specialist")
    if "product" in text_lower and "design" in text_lower:
        roles.add("Junior Product Designer")
    if "figma" in text_lower or "ux" in text_lower or "ui" in text_lower:
        roles.add("UI/UX Design Intern")
    # Marketing
    if "digital" in text_lower and "marketing" in text_lower:
        roles.add("Digital Marketing Intern")
    # Banking
    if "banking" in text_lower or "investment" in text_lower:
        roles.add("Banking / Finance Intern")

    return sorted(roles)


def parse_cv(pdf_path: str) -> dict:
    """
    Parse a CV PDF and return structured data.

    Returns:
        dict with keys: name, email, phone, location, skills, experience,
                        education, certifications, suggested_roles, raw_text
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"CV file not found: {pdf_path}")

    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text.strip():
        raise ValueError(f"Could not extract text from: {pdf_path}")

    # Extract name (first non-empty line)
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    name = lines[0] if lines else "Unknown"

    # Extract email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", raw_text)
    email = email_match.group() if email_match else ""

    # Extract phone
    phone_match = re.search(r"(?:\+91|91)?[\s-]?\d{10}|\d{3}[\s.-]\d{3,4}[\s.-]\d{4}", raw_text)
    phone = phone_match.group() if phone_match else ""

    # Extract location
    location_match = re.search(r"(?i)(bengaluru|bangalore|mumbai|delhi|pune|hyderabad|chennai|gurgaon|noida|gurugram|remote)", raw_text)
    location = location_match.group() if location_match else ""

    skills = extract_skills(raw_text)
    experience = extract_experience(raw_text)
    education = extract_education(raw_text)
    certifications = extract_certifications(raw_text)
    suggested_roles = extract_roles_from_cv(raw_text)

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "skills": skills,
        "experience": experience,
        "education": education,
        "certifications": certifications,
        "suggested_roles": suggested_roles,
        "raw_text": raw_text,
    }
