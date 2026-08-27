# 🔍 LITSEARCH — AI-Powered Multi-Portal Job Search Engine

> **Stop endlessly scrolling job boards.** LITSEARCH parses your CV, auto-generates search queries, scrapes 6 major job portals simultaneously, scores every job against your profile out of 100, and exports everything to a beautiful Excel file with skills gap analysis.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **CV Parsing** | Extracts 30+ skills, 8+ suggested roles from your PDF resume |
| **Multi-Portal Search** | LinkedIn, Naukri, Indeed, Glassdoor, Shine, Foundit — simultaneously |
| **Smart Scoring** | 100-point scoring: title match (25), skills overlap (35), keywords (15), location (15), experience (10) |
| **Skills Gap Analysis** | Shows missing skills per job — know exactly what to upskill |
| **Full-Text Enrichment** | Fetches job descriptions for top candidates, re-scores with full context |
| **Maker-Checker QC** | Rejects SERP pages, aggregate titles, duplicates — only real jobs pass |
| **Playwright Browser** | JS-heavy portals rendered in headless Chromium (subprocess-isolated) |
| **Excel Export** | 6 sheets: Top Matches, All Jobs, CV Profile, Portal Summary, Skills Gap, QC Report |
| **Freshness Filter** | Only jobs posted in last N days (default: 7) |
| **CLI with Rich UI** | Colorful terminal output with progress bars and tables |

---

## 🚀 Quick Start

### Install

```bash
# Clone the repo
git clone https://github.com/Ashishkashyap1/litsearch.git
cd litsearch

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright + Chromium (for Naukri, Indeed, etc.)
pip install playwright
playwright install chromium
```

### Run

```bash
# Basic search with your CV
python -m LITSEARCH --cv "C:\Users\you\Desktop\Your_CV.pdf"

# Search in a specific city
python -m LITSEARCH --cv resume.pdf --location Bengaluru

# Search specific portals only
python -m LITSEARCH --cv resume.pdf --portals linkedin naukri

# Custom queries
python -m LITSEARCH --cv resume.pdf --queries "financial analyst" "data analyst"

# Show top 20 matches, jobs from last 14 days
python -m LITSEARCH --cv resume.pdf --top 20 --freshness 14
```

### CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--cv`, `-c` | Path to CV PDF **(required)** | — |
| `--output`, `-o` | Custom Excel filename | `LITSEARCH_Results_<timestamp>.xlsx` |
| `--portals`, `-p` | Portals to search | all 6 |
| `--location`, `-l` | Job location filter | auto-detected from CV |
| `--max-results`, `-m` | Max results per portal per query | 15 |
| `--top`, `-t` | Top N matches to display | 10 |
| `--queries`, `-q` | Custom search queries | auto-generated from CV |
| `--freshness` | Only show jobs posted within N days | 7 |
| `--verbose`, `-v` | Debug logging | off |

---

## 📊 Results

### Test Run (Bengaluru, 8 queries, 6 portals)

```
Total Jobs Found:     20 (after QC dedup from 40 scraped)
Full-text Scored:     10 (with job descriptions fetched)
Good Matches (60+):   12
Moderate (40+):        5

Portal Health:
  ✅ LinkedIn:        40 results
  🚫 Naukri:          BLOCKED (CAPTCHA detected)
  🚫 Indeed:          BLOCKED (CAPTCHA detected)
  🚫 Glassdoor:       BLOCKED (CAPTCHA detected)
  🚫 Foundit:         BLOCKED (CAPTCHA detected)
  ⚠️  Shine:           Zero results (selector needs update)
```

### Top Matches

| # | Company | Role | Score | Skills Gap |
|---|---------|------|-------|------------|
| 1 | Circle | SEO Specialist | 79% 🔵 | data analytics |
| 2 | HSBC | Equity Research Analyst | 75% 🔵 | data analytics |
| 3 | 24 Seven Inc | Analyst – Investment Due Diligence | 75% 🔵 | — |
| 4 | JP Morgan | Financial Analyst - Associate | 73% 🔵 | — |
| 5 | Nutanix | Financial Analyst | 70% 🔵 | tableau, salary |
| 6 | Creatio | Product Designer | 70% 🔵 | — |
| 7 | ofi | Junior Compliance Analyst | 67% 🔵 | — |
| 8 | Qualcomm | Financial Analyst | 67% 🔵 | power bi, tableau, sap |
| 9 | Adobe | Product Designer – Adobe Express | 65% 🔵 | — |
| 10 | Infosys | Product Designer | 65% 🔵 | — |

### Excel Output (6 Sheets)

1. **Top Matches** — Ranked jobs with scores, skills gap, and apply links
2. **All Jobs** — Every scraped job with descriptions, matched/missing skills
3. **CV Profile** — Your extracted skills, roles, experience, education
4. **Portal Summary** — Jobs per portal + portal health status
5. **Skills Gap** — Missing skills aggregated across top jobs
6. **QC Report** — Maker-checker audit trail with reject reasons

---

## 🏗️ Architecture

```
LITSEARCH/
├── __init__.py              # Package init
├── __main__.py              # python -m LITSEARCH entry
├── cli.py                   # Rich CLI with progress bars
├── cv_parser.py             # PDF resume parser (skills, roles, experience)
├── keyword_analyzer.py      # Search query generator from CV data
├── scorer.py                # 100-point scoring engine with skills gap
├── checker.py               # Maker-Checker QC gate (rejects junk)
├── excel_export.py          # Formatted Excel with 6 sheets
├── requirements.txt         # Dependencies
└── scrapers/
    ├── __init__.py
    ├── base.py              # Polite HTTP, backoff, text utilities
    ├── linkedin.py          # Guest API scraper + description fetcher
    ├── browser.py           # Playwright scrapers (Naukri, Indeed, etc.)
    └── manager.py           # Concurrent orchestrator, portal health
```

### Scoring Formula

| Component | Weight (full-text) | Weight (title-only) | Description |
|-----------|-------------------|---------------------|-------------|
| Title Match | 25 | 55 | How well title matches your suggested roles |
| Skills Overlap | 35 | 15 | CV skills found in job description |
| Keywords | 15 | — | Domain coverage (finance, tech, writing, analysis) |
| Location | 15 | 20 | City match, remote, India cities |
| Experience | 10 | 10 | Years-of-experience heuristic |

When descriptions are unavailable (title-only mode), weight shifts to title and location. After description enrichment, full-text scoring kicks in for accurate skill matching.

---

## ⚠️ Honest Limitations

1. **Anti-bot protection**: Naukri, Indeed, Glassdoor, Foundit serve CAPTCHAs to automated browsers. The tool detects and reports this honestly rather than silently returning zero.
2. **LinkedIn rate limiting**: Guest API allows ~6-8 queries before 429. The tool backs off and stops.
3. **Selector maintenance**: Portal UIs change frequently. If a scraper shows "SELECTOR MISS", CSS selectors need updating for the new layout.
4. **No login sessions**: Tool uses public, logged-out pages only. No ToS violations.

### Recommended Alternatives for Volume

For serious job search volume without anti-bot arms races:
- **Adzuna API** (free tier): developer.adzuna.com — reliable, has descriptions
- **JSearch** (RapidAPI): Aggregates Indeed/LinkedIn/Glassdoor with descriptions included

---

## 🛠️ Installation

### Requirements

- Python 3.10+
- Playwright + Chromium (for browser-based portals)
- Internet connection

### Dependencies

```
pymupdf>=1.24.0          # PDF parsing
requests>=2.31.0         # HTTP client
beautifulsoup4>=4.12.0   # HTML parsing
lxml>=5.0.0              # HTML parser
openpyxl>=3.1.0          # Excel export
rich>=13.0.0             # CLI formatting
playwright>=1.40.0       # Browser automation
```

### Full Install

```bash
pip install pymupdf requests beautifulsoup4 lxml openpyxl rich playwright
playwright install chromium
```

---

## 📝 License

MIT License — Use freely for your job search.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch
3. Submit a PR with selector updates or new portal scrapers

---

## ⭐ Star This Repo

If LITSEARCH helped you find a job, give it a star! It motivates continued development.
