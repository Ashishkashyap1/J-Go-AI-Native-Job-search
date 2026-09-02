# 🔍 LITSEARCH — AI-Powered Multi-Portal Job Search Engine

> **Stop endlessly scrolling job boards.** LITSEARCH parses your CV, auto-generates search queries, scrapes 7 major job portals simultaneously, scores every job against your profile out of 100, and exports everything to a beautiful Excel file with skills gap analysis.
>
> 📥 **[Download Sample Output (10-day search)](sample_output_10day.xlsx)** — 20 jobs, 15 enriched with descriptions
> 📥 **[Download Sample Output (LinkedIn API)](sample_output_api.xlsx)** — 20 jobs, 10 with full descriptions

---

## ⚡ Quick Start (One Click)

### Windows (PowerShell or CMD)
```powershell
cd C:\Users\you\Desktop\Projects\LITSEARCH
.\run.bat "C:\path\to\your_cv.pdf" --location Bengaluru
```
> **Tip:** Use `.\run.bat` (with the dot-slash) in PowerShell.
> You can pass any extra flags after the CV path: `--location`, `--freshness 8`, `--top 20`, etc.

### Linux / Mac
```bash
cd ~/Desktop/Projects/LITSEARCH
chmod +x run.sh
./run.sh /path/to/your_cv.pdf --location Bengaluru
```

That's it. The script handles **everything** — installs Python deps, Playwright/Chromium, and runs the search.

---

## 📋 Manual Setup (If You Prefer)

### Step 1: Install (from inside LITSEARCH/)
```bash
cd C:\Users\you\Desktop\Projects\LITSEARCH
pip install -r requirements.txt
python -m playwright install chromium
```

### Step 2: Run (from the PARENT folder, i.e. Projects/)
```bash
cd C:\Users\you\Desktop\Projects
python -m LITSEARCH --cv "C:\path\to\your_cv.pdf" --location Bengaluru
```
> **Important:** `python -m LITSEARCH` must be run from the folder **above** `LITSEARCH/`, not from inside it.

### Step 3: Open Excel
Find `LITSEARCH_Results_<timestamp>.xlsx` in the folder — open it in Excel.

---

## 🎯 What It Searches For

LITSEARCH extracts skills from your CV and generates **fresher/early-career** job queries:

| Your Skills | Auto-Generated Queries |
|-------------|----------------------|
| Equity Research, DCF, Valuation | Junior Equity Research Analyst, Finance Trainee |
| Python, SQL, Data Analysis | Junior Data Analyst, Data Analytics Intern |
| Compliance, AML, KYC | Junior Compliance Analyst, Risk Intern |
| Proposal Writing, RFP | Junior Proposal Writer, Technical Writer |
| SEO, Content | Junior SEO Specialist, Digital Marketing Intern |
| Product Design, Figma | Junior Product Designer, UI/UX Design Intern |
| Bloomberg, Portfolio Mgmt | Fund Operations Trainee, Banking Intern |

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **CV Parsing** | Extracts 30+ skills, 20+ fresher/early-career roles from your PDF resume |
| **Multi-Portal Search** | LinkedIn (guest + API), Naukri, Indeed, Glassdoor, Shine, Foundit, JSearch — simultaneously |
| **Smart Scoring** | 100-point scoring: title match (25), skills overlap (35), keywords (15), location (15), experience (10) |
| **Skills Gap Analysis** | Shows missing skills per job — know exactly what to upskill |
| **Full-Text Enrichment** | Fetches job descriptions for top candidates, re-scores with full context |
| **Maker-Checker QC** | Rejects SERP pages, aggregate titles, duplicates — only real jobs pass |
| **Playwright Browser** | JS-heavy portals rendered in headless Chromium (subprocess-isolated) |
| **Excel Export** | 5 sheets: Top Matches, All Jobs, CV Profile, Portal Summary, QC Report |
| **Freshness Filter** | Only jobs posted in last N days (default: 7) |
| **CLI with Rich UI** | Colorful terminal output with progress bars and tables |

---

## 🖥️ CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--cv`, `-c` | Path to CV PDF **(required)** | — |
| `--output`, `-o` | Custom Excel filename | `LITSEARCH_Results_<timestamp>.xlsx` |
| `--portals`, `-p` | Portals to search | all |
| `--location`, `-l` | Job location filter | auto-detected from CV |
| `--max-results`, `-m` | Max results per portal per query | 15 |
| `--top`, `-t` | Top N matches to display | 10 |
| `--queries`, `-q` | Custom search queries | auto-generated from CV |
| `--freshness` | Only show jobs posted within N days | 7 |
| `--verbose`, `-v` | Debug logging | off |

---

## 📊 Results

### Test Run (Bengaluru, 8 queries, all portals)

```
Total Jobs Found:     20 (after QC dedup from 50 scraped)
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

---

## 🏗️ Architecture

```
LITSEARCH/
├── __init__.py              # Package init
├── __main__.py              # python -m LITSEARCH entry
├── cli.py                   # Rich CLI with progress bars
├── cv_parser.py             # PDF resume parser (skills, roles, experience)
├── keyword_analyzer.py      # Search query generator (fresher-focused)
├── scorer.py                # 100-point scoring engine with skills gap
├── checker.py               # Maker-Checker QC gate (rejects junk)
├── excel_export.py          # Formatted Excel with 5 sheets
├── requirements.txt         # Dependencies
├── run.bat                  # 🚀 One-click launcher (Windows)
├── run.sh                   # 🚀 One-click launcher (Linux/Mac)
├── sample_output_10day.xlsx # 📥 Sample: 10-day freshness search results
├── sample_output_api.xlsx   # 📥 Sample: LinkedIn API search results
└── scrapers/
    ├── __init__.py
    ├── base.py              # Polite HTTP, backoff, text utilities
    ├── linkedin.py          # Guest API scraper + description fetcher
    ├── linkedin_jobs_api.py # Fresh LinkedIn Scraper API (RapidAPI)
    ├── jsearch.py           # JSearch API (RapidAPI)
    ├── browser.py           # Playwright scrapers (Naukri, Indeed, etc.)
    └── manager.py           # Concurrent orchestrator, portal health
```

---

## ⚠️ Honest Limitations

1. **Anti-bot protection**: Naukri, Indeed, Glassdoor, Foundit serve CAPTCHAs to automated browsers. The tool detects and reports this honestly rather than silently returning zero.
2. **LinkedIn rate limiting**: Guest API allows ~6-8 queries before 429. The tool backs off and stops.
3. **Selector maintenance**: Portal UIs change frequently. If a scraper shows "SELECTOR MISS", CSS selectors need updating for the new layout.
4. **No login sessions**: Tool uses public, logged-out pages only. No ToS violations.

### Recommended Alternatives for Volume

For serious job search volume without anti-bot arms races:
- **Fresh LinkedIn Scraper API** (RapidAPI, free tier): Full descriptions, company info, 20k+ jobs/hour — https://rapidapi.com/fantastic-jobs-fantastic-jobs-default/api/fresh-linkedin-scraper-api
- **Adzuna API** (free tier): developer.adzuna.com — reliable, India-focused
- **JSearch** (RapidAPI): Aggregates Indeed/LinkedIn/Glassdoor (search endpoint may be deprecated)

---

## 🛠️ Requirements

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
