# Session 3 Learnings — Job Hunt OS

## SCHEMA & COLUMN MANAGEMENT

- Adding a column between existing columns shifts all hardcoded column letters in `batch_write_scores` — always add new columns at the END of COLUMNS list to avoid breaking scorer writes
- `open_or_create_sheet()` must check `existing[0][0] == "job_id"` not just truthiness — after a manual sheet clear, `get_all_values()` can return stale non-empty state, causing header to be skipped and data written without a header row
- When header is missing, use `insert_row(COLUMNS, 1, ...)` not `append_row` so it prepends rather than appends to existing data
- The `description` column was never in the sheet schema — scorer was getting 0 chars for every JSearch job, scoring from title only. Fixed by adding `description` as column Q (last position) to avoid shifting scoring columns
- `batch_write_scores` hardcodes column letters (J:M, O, P, Q) — known fragility, must update manually whenever COLUMNS changes. Deferred to fix after clean full run.

## SOURCES & DEDUPLICATION

- Greenhouse public API: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` — no auth required, returns full JD in one call
- Greenhouse slugs are NOT always the company name — `doordash` → `doordashusa`, `perplexity` → verified 404 (uses Ashby as `perplexity-ai`). Always verify via `boards.greenhouse.io/{slug}`
- Boards now redirect from `boards.greenhouse.io` to `job-boards.greenhouse.io` — API endpoint (`boards-api.greenhouse.io`) still works
- Companies not on Greenhouse: Ashby users = ironclad, rippling, cohere, perplexity-ai, wandb, moveworks, anyscale, mistral. Lever users = retool, thumbtack, uber. Slugs saved in `_not_on_greenhouse` key in `config/target_companies.json`
- Ledger mode (`append_new_jobs` without `clear_data_rows`) correctly deduplicates — second run with same companies produced "633 already in sheet"
- `job_id` format by source: JSearch = native hash ID, Wellfound = `wf_{id}`, VC Portfolio = `vc_{md5hash}`, Greenhouse = `gh_{slug}_{job_id}`

## PM_TITLE_TERMS & FILTERING

- Shared filter list extracted to `config/filters.py` — both `job_search.py` and `greenhouse_sources.py` import from there. Single source of truth.
- `detect_remote()` also lives in `config/filters.py` — checks title + location + description for remote/onsite/hybrid keywords across all sources
- Greenhouse filter must run AFTER normalization in `fetch_greenhouse_jobs()` not inside `_fetch_company()` — cleaner separation and single visible filter pass
- New PM_TITLE_TERMS added this session: `"strategy lead"`, `"ai strategy"`, `"product strategy"` (product lead was already present)

## JSEARCH API

- Endpoint: `/search-v2` (not `/search`) — returns `data.jobs[]` not `data[]`
- `num_pages=5` = 1 API request returning up to 50 results; 14 queries = 14 requests per run
- `date_posted: "month"` catches more roles than `"week"` without blowing quota
- Retry logic: `requests.Timeout` retries once after 10s sleep; non-timeout errors (4xx/5xx) do not retry
- Timeout increased from 15s → 30s → 60s — 60s needed for slower queries like "Senior Product Manager"
- Some queries consistently time out on first attempt but succeed on retry ("Strategy Lead Product", "Group Product Manager")

## SCORER PERFORMANCE & BUGS

- First full scorer run took ~75 seconds per job — root cause was prompt size: full resumes (~13KB) sent on every API call
- Fixed by replacing full resumes with compact bullet summaries (~25 bullets total), reducing max_tokens from 512 to 500, and reducing CALL_DELAY_SECONDS from 0.5 to 0.1
- Reducing max_tokens to 256 caused JSON truncation errors — "Unterminated string" on jobs with longer reason fields. Increased back to 500.
- Anthropic SDK default timeout is 600 seconds — a hung API call at job 69 silently blocked the entire run three times for 5+ minutes each
- Fixed by adding `timeout=30` to `client.messages.create()` and increasing retry sleep after timeout from 2s to 10s
- `APITimeoutError` now caught separately before generic `APIError` for cleaner logging
- `caffeinate -dims python3 match_scorer.py` prevents Mac sleep/display sleep from dropping network connections mid-run (`-i` alone is not enough; `-dims` covers display, idle, disk, and system sleep)
- Guardrails inline fallback works correctly when `guardrails/guardrails.md` is missing — logs a warning, does not crash
- `batch_write_scores` hardcodes column positions — known fragility, deferred until after first clean full run confirms scores are correct

## MISC

- `config/filters.py` is a Python module inside the `config/` directory — works as a namespace package in Python 3.3+ without needing `__init__.py`
- `apify_sources.py` Wellfound actor (`blackfalcondata~wellfound-scraper`) occasionally returns 502 — caught gracefully, returns 0 jobs, run continues
- VC Portfolio actor (`parseforge~vc-portfolio-jobs-aggregator-scraper`) does not return job descriptions — `description` hardcoded to `""`
- HTML stripping for Greenhouse descriptions uses stdlib `html.parser` — no extra dependencies
