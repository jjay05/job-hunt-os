# Job Hunt OS

A personal agentic job search pipeline. Discovers PM roles (or any role) across multiple sources daily, scores them against your criteria using an LLM, and surfaces the best ones for manual review.

Built by [Juhi Jain](https://www.linkedin.com/in/juhi-jain-4024a7104/), AI PM — as a portfolio project and a real tool used actively in a job search.

> Read the full builder story: [docs/builder-story-final.md](docs/builder-story-final.md)
> Read the technical learnings: [docs/technical-learnings.md](docs/technical-learnings.md)

---

## What It Does

**Skill 1: Job Discovery (`job_search.py`)**
Pulls jobs from four sources, deduplicates by job_id, pre-filters by your target titles, and appends new rows to a Google Sheet. Runs daily via GitHub Actions.

**Skill 2: LLM Match Scorer (`match_scorer.py`)**
Reads unscored rows from the sheet, sends each JD plus your candidate profile to an LLM, scores against a rubric, and writes scores back. Run manually when you want to score a batch.

**Human Gate**
You review the scored sheet, set status flags, and decide what to apply to. Nothing goes out without your decision.

---

## Architecture

```
job_search.py (daily cron)
├── JSearch (RapidAPI)        → LinkedIn, Indeed, ZipRecruiter, Glassdoor
├── Apify Wellfound Scraper   → startup and AI-first companies
├── Apify VC Portfolio        → a16z, YC, Sequoia portfolio companies
└── Greenhouse Public API     → 39 hand-picked target companies

       ↓ deduplicate by job_id
       ↓ filter by title_filter_terms
       ↓ append-only write to Google Sheet

match_scorer.py (manual)
└── reads unscored rows
└── sends JD + candidate profile to LLM
└── writes score, tier, track, reason back to sheet

You → review sheet → decide → apply
```

---

## Prerequisites

- Python 3.10+
- A Google Cloud project with Sheets API and Drive API enabled
- A Google service account with a JSON key file
- API keys for: RapidAPI (JSearch), Apify, Anthropic (or your LLM of choice)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/jjay05/job-hunt-os.git
cd job-hunt-os
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:
```
RAPIDAPI_KEY=your_rapidapi_key
APIFY_TOKEN=your_apify_token
ANTHROPIC_API_KEY=your_anthropic_api_key
```

**Getting each key:**
- RapidAPI (JSearch): [rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) — Pro tier, $25/month, 10k requests included
- Apify: [console.apify.com/account/integrations](https://console.apify.com/account/integrations) — pay per use, ~$0.10-0.20 per run
- Anthropic: [console.anthropic.com/account/keys](https://console.anthropic.com/account/keys) — pay per use, ~$2-5 per scoring batch

### 4. Set up Google Sheets

1. Create a Google Cloud project at [console.cloud.google.com](https://console.cloud.google.com)
2. Enable the Google Sheets API and Google Drive API
3. Create a service account and download the JSON key
4. Save it to `credentials/sheets_key.json`
5. The sheet will be created and shared with you automatically on first run

### 5. Configure for your role

**Edit `config/search_config.json`** — this is the only file you need to change to adapt this for any job function:

```json
{
  "search_queries": [
    "Senior Product Manager",
    "AI Product Manager"
  ],
  "title_filter_terms": [
    "product manager",
    "product lead"
  ],
  "scorer_settings": {
    "model": "claude-sonnet-4-6"
  }
}
```

For a data engineer search, change to:
```json
{
  "search_queries": [
    "Senior Data Engineer",
    "Staff Data Engineer",
    "Principal Data Engineer"
  ],
  "title_filter_terms": [
    "data engineer",
    "analytics engineer",
    "data platform"
  ],
  "scorer_settings": {
    "model": "claude-sonnet-4-6"
  }
}
```

**Edit `config/target_companies.json`** — add or remove Greenhouse slugs for companies you want to watch directly. Find a company's slug by visiting `boards.greenhouse.io/{slug}` in your browser.

### 6. Set up your candidate profile

```bash
cp config/context_store.template.json config/context_store.json
```

Edit `config/context_store.json` with your details — name, location, salary floor, target roles, dealbreakers, and resume track positioning. This file is gitignored and never pushed to GitHub.

Create your resume files at:
- `resume/resume_ai.md` — your primary resume (or AI-track resume)
- `resume/resume_adtech.md` — your domain-track resume (optional, for dual-track scoring)

---

## Running It

### Job Discovery

```bash
python3 job_search.py
```

Fetches jobs from all four sources, deduplicates, filters by your title terms, and appends new rows to the sheet. Safe to run multiple times — existing jobs are never duplicated.

### LLM Match Scorer

```bash
# Test on 10 jobs first to check calibration
python3 match_scorer.py --limit 10

# Score everything unscored
caffeinate -dims python3 match_scorer.py
```

Use `caffeinate -dims` on Mac to prevent sleep from dropping the connection mid-run. The scorer skips already-scored rows and resumes from where it left off on any crash.

**Preview mode (no writes to sheet):**
```bash
python3 match_scorer.py --preview 5
```

---

## Scoring Output

Each job gets scored across four dimensions:

| Dimension | Max Points |
|---|---|
| Domain Match | 3 |
| AI Readiness | 3 |
| Skills Match | 2 |
| Level & Scope | 2 |
| **Total** | **10** |

| Tier | Score | What to do |
|---|---|---|
| Tier 1 | 9-10 | Full effort — tailor resume, write cover letter, seek referral |
| Tier 2 | 7-8 | Apply — tailored resume, standard cover letter |
| Tier 3 | 5-6 | Spray — minimal tailoring, apply quickly |
| Skip | below 5 | Don't apply |

Hard skips override tier — roles requiring production code, sales roles, or agencies are auto-skipped regardless of score.

---

## Swapping the LLM

The scorer is model-agnostic. Change the model in `config/search_config.json`:

```json
"scorer_settings": {
  "model": "claude-haiku-4-5-20251001"
}
```

Claude Haiku is significantly cheaper and worth benchmarking against Sonnet for scoring tasks. Run both on the same 50-job batch and compare tier/track agreement. If agreement is above 90%, switch to Haiku for all batch runs.

To use a non-Anthropic model, update the API client in `match_scorer.py`. The prompt and JSON schema are model-agnostic.

---

## Automating Discovery with GitHub Actions

The daily cron runs `job_search.py` automatically. To set it up:

**1. Add these secrets to your GitHub repo** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `RAPIDAPI_KEY` | your RapidAPI key |
| `APIFY_TOKEN` | your Apify token |
| `ANTHROPIC_API_KEY` | your Anthropic key |
| `GOOGLE_SHEETS_KEY` | base64-encoded `credentials/sheets_key.json` |

To base64 encode your service account key:
```bash
base64 -i credentials/sheets_key.json
```

**2. Create `.github/workflows/daily_job_search.yml`:**

```yaml
name: Daily Job Discovery

on:
  schedule:
    - cron: '0 13 * * *'  # 5am PST = 1pm UTC
  workflow_dispatch:       # allows manual trigger from GitHub UI

jobs:
  discover:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Decode Google service account key
        run: |
          mkdir -p credentials
          echo "${{ secrets.GOOGLE_SHEETS_KEY }}" | base64 --decode > credentials/sheets_key.json

      - name: Create .env file
        run: |
          echo "RAPIDAPI_KEY=${{ secrets.RAPIDAPI_KEY }}" >> .env
          echo "APIFY_TOKEN=${{ secrets.APIFY_TOKEN }}" >> .env
          echo "ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}" >> .env

      - name: Run job discovery
        run: python3 job_search.py
```

**3. Push and test:**

Go to GitHub → Actions → Daily Job Discovery → Run workflow to trigger manually and confirm it works before relying on the cron.

---

## Running Costs

| Component | Cost |
|---|---|
| JSearch API (Pro tier) | $25/month flat, 10k requests included |
| Apify actors | ~$0.10-0.20 per discovery run |
| Greenhouse API | Free, no auth required |
| Google Sheets API | Free |
| LLM scoring (initial batch, ~700 jobs, Sonnet) | ~$3-5 one-time |
| LLM scoring (ongoing, manual chat) | ~$0 — paste new jobs to Claude directly |
| **Daily discovery only** | **~$0.10-0.20/run** |

**Recommended approach:** run the batch scorer once for the initial backlog, then score new daily jobs manually by pasting them into Claude chat. At 20-50 new jobs per day, manual scoring is faster and costs nothing.

---

## Known Limitations

- JSearch returns partial descriptions (~500 chars) on some listings — Greenhouse returns full JDs
- VC Portfolio actor returns no job descriptions — these score on title and company only
- Remote detection is text-based — reliable for JSearch and Greenhouse, less reliable for VC Portfolio
- `batch_write_scores` in `sheets.py` uses hardcoded column letters — will break if you add columns in the middle of the schema. Always add new columns at the end of `COLUMNS`.
- Python 3.9 is past end of life — upgrade to 3.11+ recommended

---

## Repo Structure

```
job-hunt-os/
├── config/
│   ├── search_config.json        ← edit this for your role
│   ├── context_store.template.json  ← copy to context_store.json and fill in
│   ├── filters.py                ← remote detection logic
│   └── target_companies.json     ← Greenhouse company slugs
├── resume/                       ← gitignored, add your own
├── credentials/                  ← gitignored, add your service account key
├── docs/
│   ├── builder-story-final.md    ← why and how this was built
│   └── technical-learnings.md   ← technical decisions and bugs
├── job_search.py                 ← discovery orchestrator
├── apify_sources.py              ← Wellfound + VC portfolio
├── greenhouse_sources.py         ← target company boards
├── match_scorer.py               ← LLM scoring pipeline
├── sheets.py                     ← Google Sheets read/write
├── .env.example                  ← copy to .env and fill in
└── requirements.txt
```

---

## Built With

Python, Claude API (Sonnet 4.6), Google Sheets API, JSearch (RapidAPI), Apify, Greenhouse public API, GitHub Actions.

---

*Built by [Juhi Jain](https://www.linkedin.com/in/juhi-jain-4024a7104/) — AI PM building in public.*
