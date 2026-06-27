# Job Hunt OS: Additional Learnings (Session 2)

---

## Location Fetching Learning
API field reliability: always validate against reality
job_is_remote from JSearch returns False for most jobs even when the role is genuinely remote. The field is unreliable because most employers don't explicitly set it in their postings. JSearch defaults to False on missing data instead of None or Unknown, which makes it silently wrong rather than obviously empty.
Lesson: never trust a boolean field from a third-party API without spot-checking it against real data. A field that looks populated is worse than a missing field because it gives false confidence.
Fix: detect remote status from free text instead. Parse title, location, and description for keywords like "remote", "work from home", "distributed", "anywhere in the US". Text-based detection on real content outperforms a structured field that isn't reliably populated by the data source.
Broader principle: structured fields in job APIs (salary, remote, employment type) are sparse and unreliable. Free text fields (title, description) are always populated and always accurate. Build your detection logic on text, use structured fields only as a secondary signal.

## Pipeline Architecture Learnings

### Modules vs runnable scripts: know the difference

`greenhouse_sources.py` was built as a module with a `fetch_greenhouse_jobs()` function but no `if __name__ == "__main__"` block. That means it can only be called by `job_search.py`, not run standalone. When I wanted to test Greenhouse slugs without burning JSearch API requests, I had no way to do it.

Fix: always add a standalone test mode to every source module from day one. One `if __name__ == "__main__"` block at the bottom that calls the main function and prints results. Costs 3 lines, saves you from burning API credits on every debug cycle.

### The orchestrator pattern

The final pipeline structure is:
```
job_search.py          ← orchestrator, runs everything
├── apify_sources.py   ← Wellfound + a16z/VC
└── greenhouse_sources.py  ← target company boards
```

One command runs all sources, merges, deduplicates, filters, and writes to the sheet. Each source module is independently testable. This is the right architecture for a sequential skill pipeline.

---

## Data Source Learnings

### Greenhouse has a free public API, no authentication needed

Every company on Greenhouse exposes a public job board endpoint:
```
https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
```

The `?content=true` param returns the full job description in one call. No API key, no scraping, no Apify credits. Just a plain HTTP GET.

This is significantly cleaner than scraping LinkedIn or Indeed. For target companies you care about deeply, Greenhouse direct is better than JSearch aggregation because it returns all open roles regardless of posting date, not just the last 7-30 days.

### Date filtering is a coverage tradeoff, not a quality filter

I started with `date_posted: "week"` thinking fresher jobs = better signal. The Attentive "Lead PM, First-Party Data Platform" role proved this wrong: posted 3 months ago, still open, perfect match, completely missed by the pipeline.

Changed to `date_posted: "month"`. First run will be large (400-600 raw jobs) but dedup handles overlap across runs. After the first run, subsequent runs only add net new jobs. The one-time cost of a bigger first run is worth the coverage gain.

Key insight: a job that's been open for 60 days is not a worse opportunity. It means the company hasn't found the right person yet. That's a signal to move faster, not skip it.

### Greenhouse returns all open jobs, date-agnostic

Unlike JSearch which filters by posting date, Greenhouse returns everything currently live. This means the PM title pre-filter does more work: a company like Stripe might have 200 open roles, only 5-8 of which are PM roles. Without the filter, you'd flood the sheet with engineering and design roles.

Always apply `PM_TITLE_TERMS` before writing Greenhouse results to the sheet.

### Slugs are not always obvious

A company's Greenhouse slug is the URL-friendly version of their name but it's not always predictable:
- "Scale AI" might be `scaleai` or `scale` or `scale-ai`
- "Together AI" might be `togetherai` or `together`
- "Weights & Biases" is `wandb` not `weights-biases`
- Some companies (Anthropic, Mistral) may not use Greenhouse at all

The 404 handler is essential: log the miss, continue, never crash. After the first run, audit the 404 list and look up correct slugs by visiting `boards.greenhouse.io/{slug}` directly in a browser.

---

## Coverage Strategy Learnings

### Three-layer coverage model

After adding Greenhouse, your discovery stack covers three distinct layers:

**Layer 1: Broad market (JSearch)**
LinkedIn, Indeed, ZipRecruiter, Glassdoor via Google for Jobs aggregation. Catches everything posted publicly in the last 30 days. High volume, some noise.

**Layer 2: Startup-specific (Apify)**
Wellfound for startup and AI-first companies. a16z/VC Portfolio for VC-backed companies across Sequoia, YC, Greylock, and 9 others. Lower volume, higher signal for AI PM roles.

**Layer 3: Target company watchlist (Greenhouse)**
Direct API access to job boards of 51 specific companies you've hand-selected. Returns all open PM roles regardless of date. Highest signal, zero noise from irrelevant companies.

Each layer catches jobs the others miss. That's the point of the three-layer design.

### The append-only principle is non-negotiable

The original `job_search.py` called `sheets.clear_data_rows(sheet)` on every run. This would have wiped every manual status update (applied, interviewing, skipped) on every run.

The sheet is a permanent ledger shared between the pipeline and you. The pipeline owns discovery and scoring columns. You own status and notes columns. The pipeline must never overwrite human inputs.

Rule: in any system where automation and humans share a data store, automation writes append-only to its own columns and never touches human-owned columns. This is not an engineering preference. It is a product requirement.

---

## Cost Model Update

| Source | Cost per run |
|---|---|
| JSearch API (Pro, 10k/month) | $0 included |
| Apify Wellfound + a16z/VC | ~$0.10-0.20 |
| Greenhouse (public API) | $0 free |
| Claude scoring (~200 jobs, full JD) | ~$2-8 |
| **Total per run** | **~$2-8** |

Greenhouse adds zero marginal cost while adding 51 target companies worth of coverage. Best ROI of any source added so far.

---

## What's Still Pending

- Fix Greenhouse 404 slugs after first run
- Run match_scorer.py on full batch, review summary counts
- QA: manually check 10 scored jobs against LinkedIn to validate coverage
- Guardrails formally saved to guardrails/guardrails.md
- Evals: log skips and edits as feedback signals
- Digest: email or Slack summary of Tier 1 and Tier 2 jobs daily
- Referral lookup via Apify LinkedIn (Skill 3)
- Write docs/system-design.md
- Write README.md
- GitHub publish
