# What's Next — Job Hunt OS

_Last updated: 2026-06-28 (end of Session 3)_

---

## Current State

- **Sheet**: 742 jobs ingested (633 from prior run + 109 new); ~109 rows scored, rest unscored
- **Sources active**: JSearch (14 queries, ~475 jobs), Apify VC + Wellfound, Greenhouse (39 companies, 355 PM jobs out of 6,756 total)
- **Scorer**: Working, with timeout=30 + retry, compact resumes, max_tokens=500
- **Columns**: job_id, title, company, location, remote, salary_text, url, source, posted_at, ai_score, adtech_score, match_flag, recommended_track, cover_letter, status, notes, description

---

## Immediate Next

### 1. Full scorer run (IN PROGRESS / RUN THIS)
```bash
caffeinate -dims python3 match_scorer.py
```
Run with `caffeinate -dims` to prevent Mac sleep from killing the run mid-way.

### 2. After scorer completes: QA 10 high-scoring jobs
- Filter sheet by `ai_score >= 8` or `match_flag = Strong`
- Cross-check each against the real LinkedIn posting
- Verify the scorer is not hallucinating or over-rewarding generic roles

---

## Short-Term Fixes

### Fix hardcoded column positions in batch_write_scores
`sheets.py` currently hardcodes `J:M` for scores, `O` for status, `P` for notes, `Q` for description. These break whenever COLUMNS shifts.
- Solution: derive column letters dynamically from `COLUMNS.index(field)` + `chr(ord('A') + idx)` 
- Deferred until after first clean full scorer run confirms current hardcoding is correct

### Add parallelism to scorer
- Replace sequential loop with `concurrent.futures.ThreadPoolExecutor(max_workers=5)`
- Each worker calls `_call_claude()` independently
- `batch_write_scores` continues as a single batch write after all workers finish
- Estimated speedup: 5x (from ~15s/job to ~3s/job)

---

## Medium-Term

### Write README.md + system-design.md
- README: how to run each script, env setup, API keys needed
- system-design.md: architecture diagram (sources → normalize → dedup → sheet → scorer → output)

### Deploy via GitHub Actions cron
- Trigger `job_search.py` daily at 9 AM PST
- Trigger `match_scorer.py` after job search completes (or on a separate schedule)
- Requires: secrets for RAPIDAPI_KEY, APIFY_TOKEN, ANTHROPIC_API_KEY, sheets_key.json
- Store `sheets_key.json` as a base64-encoded GitHub secret, decode at run time

---

## Low Priority / Deferred

### Ashby + Lever scrapers
Companies confirmed NOT on Greenhouse:
- **Ashby**: ironclad, rippling, cohere, perplexity-ai, wandb, moveworks, anyscale, mistral
- **Lever**: retool, thumbtack, uber

Ashby public API: `https://api.ashbyhq.com/posting-api/job-board/{slug}` (verify, may need auth)
Lever public API: `https://api.lever.co/v0/postings/{slug}?mode=json`

### Move guardrails inline text to guardrails/guardrails.md
- `match_scorer.py` currently has GUARDRAILS as a Python string literal
- More maintainable as a separate file with clear sections
- When file is missing, scorer logs a warning and falls back to inline string — safe to defer

### Slack/email digest
- Not needed — sheet is checked daily manually
- Reopen if job volume makes daily sheet review burdensome

---

## Known Fragilities (document, don't fix yet)

| Issue | Location | Risk | Mitigation |
|---|---|---|---|
| Hardcoded column letters | `sheets.py` batch_write_scores | Breaks on any column shift | Fix before next schema change |
| Apify VC actor returns no descriptions | `apify_sources.py` | VC jobs scored on title only | Accept for now |
| JSearch deduplication is by job_id | `sheets.py` append_new_jobs | Same job from two queries = one row (correct) | No action needed |
| Wellfound actor returns 502 occasionally | `apify_sources.py` | 0 Wellfound jobs for that run | Logged, non-fatal |
