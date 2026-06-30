# Job Hunt OS: Technical Learnings
*Consolidated across all build sessions — organized by theme*

---

## 1. Sheet Schema & Column Management

**Always add new columns at the END of the COLUMNS list.**
Adding a column between existing columns shifts every hardcoded column letter in `batch_write_scores`. One schema change breaks all score writes silently.

**`description` was never in the sheet schema.**
`job_search.py` fetched full JDs from every source. `sheets.py` only wrote columns listed in `COLUMNS`. Description was not in `COLUMNS`. Result: 721 jobs in the sheet with empty description fields, scorer running on title only. No error, no warning. Fixed by adding `description` as the last column and clearing and re-running discovery.

**`open_or_create_sheet()` must check `existing[0][0] == "job_id"`, not just truthiness.**
After a manual sheet clear, `get_all_values()` can return stale non-empty state. A truthy check passes even without a header row, causing data to be written without headers.

**Use `insert_row(COLUMNS, 1, ...)` not `append_row` for header recovery.**
`insert_row` prepends to row 1. `append_row` adds to the bottom. When recovering a missing header, you want row 1, not row 674.

**`batch_write_scores` hardcodes column letters (J:M, O, P, Q).**
Known fragility. These break whenever COLUMNS shifts. Fix before any future schema change: derive column letters dynamically from `COLUMNS.index(field)` + `chr(ord('A') + idx)`.

---

## 2. Data Sources

### JSearch (RapidAPI)
- Endpoint: `/search-v2` not `/search` — returns `data.jobs[]` not `data[]`
- `num_pages=5` = 1 API request returning up to 50 results. 14 queries = 14 requests per run.
- `date_posted: "month"` covers more roles than `"week"` without blowing quota. A job open for 60 days is not a worse opportunity — it means the company hasn't found the right person yet.
- Timeout increased from 15s to 60s — needed for slower queries like "Senior Product Manager"
- Retry logic: `requests.Timeout` retries once after 10s sleep. Non-timeout errors (4xx/5xx) do not retry.
- Some queries consistently timeout on first attempt but succeed on retry.
- Returns partial descriptions (~500 chars preview) on some listings — not full JDs.

### Greenhouse (Public API)
- Endpoint: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
- No authentication required. Full JDs returned in one call. Best cost-to-signal ratio of any source.
- Returns all open roles regardless of posting date — apply PM title pre-filter after fetching.
- Slugs are not always the company name: `doordash` → `doordashusa`, `perplexity` → 404 (uses Ashby as `perplexity-ai`). Verify via `boards.greenhouse.io/{slug}` in a browser.
- Boards redirect from `boards.greenhouse.io` to `job-boards.greenhouse.io` — the API endpoint (`boards-api.greenhouse.io`) still works.
- Companies NOT on Greenhouse:
  - **Ashby**: ironclad, rippling, cohere, perplexity-ai, wandb, moveworks, anyscale, mistral
  - **Lever**: retool, thumbtack, uber
- HTML stripping uses stdlib `html.parser` — no extra dependencies needed.
- Add `time.sleep(0.5)` between company fetches to avoid rate limiting across 39 companies.

### Apify (Wellfound + VC Portfolio)
- Wellfound actor (`blackfalcondata~wellfound-scraper`): `enrichDetail=True` required for full descriptions. Occasionally returns 502 — caught gracefully, returns 0 jobs, run continues.
- VC Portfolio actor (`parseforge~vc-portfolio-jobs-aggregator-scraper`): does not return job descriptions. `description` hardcoded to `""`. These jobs score on title and company only.
- Both actors run synchronously via `run-sync-get-dataset-items` — HTTP timeout should be actor timeout + 15s.

### Source Coverage Model
Three layers, each catching jobs the others miss:
- **Layer 1 (JSearch):** broad market, LinkedIn/Indeed/ZipRecruiter/Glassdoor, high volume
- **Layer 2 (Apify):** startup-specific, Wellfound + VC-backed companies, lower volume, higher signal for AI PM roles
- **Layer 3 (Greenhouse):** target company watchlist, direct API, all open roles regardless of date, highest signal

---

## 3. Deduplication & Ledger Mode

**job_id format by source:**
- JSearch: native hash ID from API
- Wellfound: `wf_{native_id}`
- VC Portfolio: `vc_{md5hash of url+title}`
- Greenhouse: `gh_{slug}_{job_id}`

**Append-only is non-negotiable.**
The sheet is shared between the pipeline and the user. Pipeline owns discovery and scoring columns. User owns status and notes. The pipeline reads existing job_ids from column A before every run and skips any already present. It never calls `clear_data_rows`. It never overwrites user-set status values.

**Dedup confirmed working:** second discovery run with same companies produced "633 already in sheet, 109 new."

---

## 4. Remote Detection

**`job_is_remote` from JSearch is unreliable.**
Returns `False` for most jobs even when the role is genuinely remote. Most employers don't explicitly set this field. JSearch defaults to `False` on missing data instead of `None`, making it silently wrong rather than obviously empty.

**Fix: detect from free text.**
Parse title, location, and description for keywords: "remote", "work from home", "distributed", "anywhere in the US", "hybrid". Text-based detection on real content outperforms a structured field that isn't reliably populated.

**Reliability by source:**
- JSearch: remote detection from free text, reliable
- Greenhouse: remote detection from free text, reliable
- Wellfound: location field is a list of city names, remote detection from text, reliable
- VC Portfolio: no description, detection from title and location only, less reliable

---

## 5. PM Title Filter

**`PM_TITLE_TERMS` lives in `config/filters.py`** — shared by `job_search.py` and `greenhouse_sources.py`. Single source of truth. `detect_remote()` also lives there.

**`config/filters.py` works as a namespace package** in Python 3.3+ without needing `__init__.py`.

**Filter grows organically and gets messy.** "product lead" was added twice across sessions. Every term should have a comment explaining what it catches. Audit periodically.

**Greenhouse filter runs AFTER normalization** in `fetch_greenhouse_jobs()`, not inside `_fetch_company()`. Cleaner separation, single visible filter pass.

---

## 6. Scorer Design & Performance

### Prompt Architecture
The prompt sent to Claude per job contains:
1. Job posting (title, company, location, salary, description up to 5,000 chars)
2. Compact candidate profile (name, YOE, location, salary floor, seniority band, track positioning)
3. Compact resume summaries (~25 bullets total across both tracks, static at module load)
4. JSON schema with scoring rules embedded

**What was removed from the prompt:**
- Full resume text (~13KB) — replaced with 25-bullet summaries. No meaningful loss in scoring quality.
- Full eval framework rubric (8.6KB) — contained cover letter advice, LinkedIn outreach tips, negotiation guidance. None relevant to scoring. Rubric logic is embedded in the JSON schema. Removing it saved ~2,000-2,500 tokens per call.

### Token Settings
- `max_tokens=400` — 256 caused JSON truncation on jobs with longer reason fields. 512 was wasteful. 400 is the right ceiling.
- `CALL_DELAY_SECONDS=0.1` — 0.5 was overly conservative for Sonnet rate limits at this volume.

### Timeouts
- Anthropic SDK default timeout is **600 seconds**. Without an explicit timeout, a hung call blocks the entire run for up to 10 minutes with no output.
- Fix: `timeout=30` on every `client.messages.create()` call.
- On `APITimeoutError`: log, sleep 10 seconds, retry once. 10s sleep gives the connection time to clear (2s was too short after a 30s hang).
- Worst case per stuck job: 30s + 10s + 30s = 70 seconds, then log error and move on.

### Retry Logic
- 2 attempts per job for both JSON parse failures and API errors.
- `APITimeoutError` caught separately before generic `APIError` for cleaner logging.
- `APIError` with `status_code == 400` and "credit" in message: raise `CREDIT_EXHAUSTED`, flush scores, exit cleanly. Do not retry — credit exhaustion is not transient.

### Batch Writing
- Accumulating all updates and writing at the end = losing everything on any crash.
- Fix: flush `updates` to sheet every 25 jobs inside the scoring loop. Final flush after loop catches remainder.
- Worst-case loss on crash: 25 jobs.

### Mac Sleep
- `caffeinate -dims python3 match_scorer.py` prevents Mac sleep from dropping connections mid-run.
- `-i` alone is not enough. `-dims` covers display sleep, idle sleep, disk sleep, and system sleep.

---

## 7. Model Selection

**Current: Claude Sonnet 4.6**
Mid-tier model appropriate for an evaluation and classification task. Does not need to generate — needs to read, match, and return structured JSON. Sonnet handles this reliably.

**Recommended next test: Claude Haiku**
Significantly cheaper and faster. Run a 50-job comparison between Sonnet and Haiku on the same batch. Check score agreement on tier and track. If agreement is above 90%, switch to Haiku for all batch runs.

**Scoring prompt is model-agnostic.** The JSON schema, rubric logic, and guardrails are all in the prompt. Swapping models requires changing one string in `match_scorer.py`.

---

## 8. GitHub & Version Control

**GitHub authentication requires a Personal Access Token (PAT), not a password.**
GitHub stopped accepting passwords in 2021. Generate a PAT at github.com → Settings → Developer settings → Personal access tokens → Tokens (classic). Scope: `repo`.

**Embed token in remote URL:**
```bash
git remote set-url origin https://USERNAME:TOKEN@github.com/USERNAME/repo.git
```

**`.gitignore` before first commit.** Must cover:
```
.env
credentials/
outputs/
__pycache__/
*.pyc
.DS_Store
```

**`.DS_Store` committed accidentally** — remove with:
```bash
git rm --cached .DS_Store
git commit -m "remove .DS_Store"
git push
```

**Only changed files appear per commit.** Git tracks diffs, not full snapshots. Three files changed = three files in the commit, regardless of repo size.

**Commit before ending every Claude Code session.** Claude Code context window fills and resets. Code lives on disk, not in memory — but only if committed.

---

## 9. GitHub Actions Deployment

**Cron for 5am PST:**
```yaml
on:
  schedule:
    - cron: '0 13 * * *'  # 1pm UTC = 5am PST
  workflow_dispatch:  # manual trigger
```

**Secrets needed:**
| Secret | Value |
|---|---|
| `RAPIDAPI_KEY` | from `.env` |
| `APIFY_TOKEN` | from `.env` |
| `ANTHROPIC_API_KEY` | from `.env` |
| `GOOGLE_SHEETS_KEY` | base64-encoded `sheets_key.json` |

**Base64 encode the service account JSON:**
```bash
base64 -i credentials/sheets_key.json
```
Store the full output as `GOOGLE_SHEETS_KEY`. Decode at runtime in the workflow:
```yaml
- run: echo "${{ secrets.GOOGLE_SHEETS_KEY }}" | base64 --decode > credentials/sheets_key.json
```

**Never paste your service account private key in plain text anywhere.** Rotate immediately if exposed: Google Cloud Console → IAM & Admin → Service Accounts → Keys → delete and regenerate.

---

## 10. Cost Management

**Estimate cost before any batch run.**
Formula: `num_jobs × avg_tokens_per_call × price_per_token`

With optimised prompt (compact resumes, no rubric, 5000 char JD cap):
- Input: ~1,500 tokens/job
- Output: ~400 tokens/job
- Total: ~1,900 tokens/job on Sonnet 4.6
- Cost: ~$0.003-0.005 per job
- 700 jobs: ~$2-4

**Ongoing strategy:** batch scorer for initial load only. New daily jobs (20-50/run) scored manually in Claude chat at zero API cost.

**Credit exhaustion** burns 2x retries per job if not caught explicitly. Handle `status_code == 400` with "credit" in message as a hard stop, not a retry.

---

## 11. Known Fragilities

| Issue | Location | Risk | Fix |
|---|---|---|---|
| Hardcoded column letters | `sheets.py batch_write_scores` | Breaks on any column shift | Derive dynamically from COLUMNS index |
| VC Portfolio returns no descriptions | `apify_sources.py` | VC jobs scored on title only | Accept or find alternative actor |
| JSearch returns partial descriptions | JSearch API | Thin scoring signal for JSearch jobs | Greenhouse is primary source for full JDs |
| Wellfound actor returns 502 occasionally | `apify_sources.py` | 0 Wellfound jobs for that run | Logged, non-fatal, retry next run |
| Remote column unreliable for Apify VC | `apify_sources.py` | "Unknown" for most VC jobs | Accept, read JD manually |
| Python 3.9 past end of life | System | google-auth and urllib3 warnings | Upgrade to Python 3.11+ |

---

## 12. Lessons That Apply Beyond This Project

**Silent failures are the hardest bugs.** A column missing from a schema, an SDK default timeout, a boolean field that defaults to False instead of None — none of these throw errors. They just produce wrong output quietly. Defensive programming means validating data at every handoff, not just at the edges.

**Trace data from source to storage to consumption.** The description bug lived between two files written in different sessions. Neither file was wrong in isolation. The gap was in the handoff.

**Prompt size at scale is a product decision, not an engineering detail.** Every token you add to a prompt that runs 700 times costs money and adds latency. Audit every section of a batch prompt: is this here because it's necessary, or because it was easy to include?

**Write incrementally for any long-running process.** Never accumulate state in memory across hundreds of operations. Flush to persistent storage as you go.

**Match model to task complexity.** Don't default to the most powerful model. Evaluate, classify, match — these are not generation tasks. A smaller, faster, cheaper model may perform identically and cost 10x less.

**The human gate belongs where stakes are highest, not where automation is easiest.**
