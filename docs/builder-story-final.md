# Job Hunt OS: Builder Story
*By Juhi Jain, AI PM — built in public*

---

## Why I Built This

I was five weeks into a job search and spending 2-3 hours a day manually checking LinkedIn, Indeed, and Wellfound for PM roles. I was copying job descriptions into documents, scoring them in my head, writing cover letters from scratch, and tracking everything in a messy spreadsheet I kept forgetting to update.

I am a product manager who spent years building AI automation systems for other people's workflows. The irony of doing my own job search manually was not lost on me.

So I built the Job Hunt OS: an agentic pipeline that finds jobs across multiple sources, scores them against my actual criteria, and surfaces the best ones so I can focus on what only I can do — decide, reach out, and apply.

---

## The Core Product Decision: What to Actually Automate

The most important decision I made was identifying the right problem to solve.

A job search pipeline has four stages: discovery, scoring, tailoring, and applying. I could have tried to automate all four. I didn't.

Here's why:

**Discovery is the real bottleneck.** Finding relevant roles across LinkedIn, Wellfound, VC portfolio boards, and target company career pages manually takes 2-3 hours a day. It's repetitive, it's exhausting, and it's the stage where I was most likely to miss something good. This is where automation creates the most leverage.

**Scoring, tailoring, and applying all require me.** I have done these manually dozens of times. I know what a good match looks like. I know how to tailor a cover letter. I know when to apply and when to pass. These steps benefit from AI assistance but they should never run without my eyes on them. The stakes are too high — every application goes out under my name.

So I optimised aggressively for discovery: four sources, 14 search queries, full JD ingestion, deduplication, and a daily cron. I built scoring as a one-time batch tool to clear the initial backlog, then deliberately switched to manual scoring in Claude chat for ongoing use to avoid API costs. Tailoring, referrals, and applications stayed manual with a human gate.

This is the decision I would lead with in any interview about this project. Knowing what not to automate is the harder product judgment.

---

## What I Built

A sequential skill pipeline with one human gate before any application is sent.

**Skill 1: Job Discovery (primary build)**

Pulls PM roles from four sources on a daily cron:

- **JSearch (RapidAPI):** aggregates LinkedIn, Indeed, ZipRecruiter, and Glassdoor via Google for Jobs. 14 broad queries ("Senior Product Manager", "AI Product Manager", "Director of Product"), up to 50 results per query, 30-day lookback window.
- **Apify VC Portfolio Jobs:** a16z, Sequoia, YC, Greylock, and 6 more VC portfolio job boards via a single actor.
- **Apify Wellfound Scraper:** startup and AI-first company listings, enriched with full descriptions.
- **Greenhouse Public API:** direct access to job boards of 39 hand-selected target companies. No authentication required. Full JDs returned in one call via `?content=true`.

Raw results flow through a PM title keyword pre-filter, get deduplicated by job_id, and append to a Google Sheet. The sheet is a permanent ledger — it never clears. Human-owned columns (status, notes) are never overwritten by the pipeline.

**Skill 2a: LLM Match Scorer (batch, one-time)**

Reads each unscored job row, sends JD plus compact resume summaries to Claude using a 9-point rubric across four dimensions: domain match, AI readiness, skills match, and level/scope. Returns score, tier, track (AI/ADTECH/DUAL/LOW MATCH), recommended resume, and a reason. Writes back to the sheet in batch.

Hard skips fire automatically for roles requiring production code, sales roles, or agency models.

**Human Gate**

I review the scored sheet, read the reasons, set status flags manually. Nothing gets applied without my decision.

**Skill 2b, 3, 4: Deliberately not built**

Tailoring, referral lookup, and auto-apply are scoped but paused. This was a product decision, not a gap. See reasoning above.

---

## Model Choice and Why

**Scorer: Claude Sonnet 4.6**

The task is evaluation and matching, not generation. I don't need the model to be creative — I need it to read a job description and a candidate profile and return a structured JSON object with consistent scores.

Sonnet 4.6 is a mid-tier model that handles structured reasoning well without the cost of Opus. For a batch job running 700+ calls, cost matters.

**What I'd try next: Claude Haiku**

Haiku is significantly cheaper and faster. The scoring task — classify a role against a rubric, return JSON — is likely within Haiku's capability. I'd run a 50-job comparison between Sonnet and Haiku on the same batch and check score consistency. If agreement is above 90% on tier and track, I'd switch to Haiku for all future batch runs.

This is the kind of model selection decision an AI PM should be making: match model capability to task complexity, don't default to the most powerful option.

**Why not GPT-4 or Gemini?**

I work in the Claude ecosystem (Claude Code, Claude chat, Claude API) throughout this project. Keeping the scorer in the same ecosystem reduces context-switching and lets me use the same API key and billing account. For a solo portfolio project, consistency has value. For a production system, I'd benchmark across providers before committing.

---

## Architecture Decisions

### Sequential skills over multi-agent

I deliberately chose a linear pipeline over a multi-agent setup. One script per skill, each reading from and writing to the same Google Sheet. No agent orchestration framework, no complex handoffs.

Why: simpler to debug, easier to explain, faster to ship. When discovery breaks, I know exactly where to look. When the scorer misbehaves, I can read the prompt directly. Transparency over sophistication.

For a solo-built portfolio project, clarity is the right architecture choice. Multi-agent would have been impressive on a diagram and painful to debug at 2am.

### The sheet as shared ledger

The Google Sheet is not a cache or a staging area. It is the system of record shared between the pipeline and me.

The pipeline owns: job_id, title, company, location, remote, salary_text, url, source, posted_at, description, ai_score, adtech_score, match_flag, recommended_track, notes.

I own: status, cover_letter.

The pipeline uses append-only writes. It reads existing job_ids before every run and skips any already in the sheet. It never clears, never overwrites human-set values.

This is a product requirement, not an engineering preference. In any system where automation and humans share a data store, the automation must play by the human's rules.

### Cast wide, filter via scoring

My first instinct was specific search queries: "AI Product Manager Seattle." Near-zero results. Job titles don't match search strings precisely.

Right design: broad queries, pull everything, let the scorer filter by fit. The PM title pre-filter handles obvious noise. The scorer handles the rest.

Permissive at ingestion, discriminating at evaluation. This principle applies everywhere.

### Manual tailoring was the right MVP decision

I designed auto-tailoring but stopped and asked: how often will I actually apply to more than 5 jobs in a week, seriously? The honest answer: 3-5.

Auto-tailoring 40 jobs before I've reviewed the scores is backwards. Score first, decide which ones deserve effort, tailor manually for the ones that matter. Pasting a JD into Claude chat and getting a tailored cover letter in 10 minutes is faster, cheaper, and keeps me in control of every word that goes out under my name.

This is how I think about human-in-the-loop design: put the gate where the stakes are highest, not where it's easiest to automate.

---

## What Went Wrong (and What I Learned)

### Silent data loss: the description column bug

The most expensive bug in the project. `job_search.py` was fetching full job descriptions from every source. But `sheets.py` only wrote columns explicitly listed in `COLUMNS`. Description was never added to `COLUMNS`.

Result: 721 jobs in the sheet, every description field empty. The scorer was running on title and company name only. Scores were meaningless. No error, no warning — just silently wrong output.

Fix: added description as the last column in `COLUMNS`, re-ran discovery, cleared and rebuilt the sheet.

Lesson: trace data from source to storage to consumption across every file it touches. A bug that lives between two files written in different sessions is the hardest kind to find. Silent failures are more dangerous than crashes.

### The default SDK timeout is 600 seconds

The Anthropic SDK default timeout is 10 minutes. Without an explicit `timeout=30` on `client.messages.create()`, a single hung API call at job 69 blocked the entire run for 5+ minutes — three times. No error, no output, just silence.

Fix: `timeout=30` on every Claude call, `APITimeoutError` caught separately, 10-second sleep before retry.

Lesson: never assume library defaults are sane for your use case. Always set explicit timeouts on external calls.

### Prompt size drove both cost and speed

First batch run: 75 seconds per job. $15.89 burned in one day before the run completed.

Root cause: full resume text (~13KB) sent on every API call, plus the full eval framework rubric (8.6KB, which included cover letter advice and LinkedIn outreach tips irrelevant to scoring).

Fix: compact 25-bullet resume summaries replacing full text, rubric removed from prompt (scoring logic already embedded in the JSON schema), max_tokens reduced from 512 to 400.

Lesson: prompt size directly drives cost and latency. Audit every token in a prompt that runs at scale. The eval framework rubric was in the prompt because it was easy to include — not because it was necessary.

### Batch write at the end means losing everything on a crash

Initial design: accumulate all scores in an `updates` list, write to sheet once at the end. On any crash — credit exhaustion, Mac sleep, kill signal — all scored-but-not-written jobs were lost and the run had to restart from the beginning.

Fix: flush to sheet every 25 jobs inside the scoring loop. Worst-case loss on crash is now 25 jobs.

Lesson: for any long-running batch job, write incrementally. Never accumulate state in memory across hundreds of operations.

### Credit exhaustion retried every failing job twice

When Anthropic API credits ran out, every subsequent job hit a 400 error. The retry logic caught it as a generic `APIError` and retried after 2 seconds — also failing. The script then moved to the next job and failed it twice too, burning through all remaining jobs 2x before stopping.

Fix: detect `status_code == 400` with "credit" in the error message, raise a `CREDIT_EXHAUSTED` signal, flush pending scores, exit cleanly.

Lesson: different error types need different handling. Not all API errors are transient. Credit exhaustion is permanent until you top up — retrying is just waste.

---

## Running Costs

| Component | Cost per run |
|---|---|
| JSearch API (Pro tier, 10k req/month) | $0 included |
| Apify actors (VC + Wellfound) | ~$0.10-0.20 |
| Greenhouse public API | $0 free |
| Claude API scoring (initial batch, ~700 jobs) | ~$3-5 optimised |
| Google Sheets API | Free |
| **Daily discovery (no scoring)** | **~$0.10-0.20** |
| **One-time batch score (700 jobs)** | **~$3-5** |

After the initial batch score, new daily jobs (20-50 per run) are scored manually in Claude chat at zero API cost. Discovery runs daily on GitHub Actions for ~$0.10-0.20 per run.

For a $200k+ job search, this math is obvious.

---

## What I Would Do Differently

**Start with the sheet schema.** Design the full column list before writing a single line of code. Adding columns mid-build shifts hardcoded downstream references and causes silent data loss.

**Write one integration test per skill.** I debugged by running the full pipeline and reading output. A test that checks "does the scorer return valid JSON with all required fields" would have caught the description truncation bug in 30 seconds.

**Set explicit timeouts on every external call from day one.** SDK defaults are not your friend at scale.

**Estimate cost before running any batch job.** I calculated a rough cost estimate early in the project and never updated it as job count grew from 88 to 773. Always re-estimate before a full run.

**Flush to sheet incrementally, never at the end.** Any process that runs for more than 10 minutes should write progress as it goes.

---

## The Portfolio Angle

I built this because I needed it. That is the best possible reason to build something.

But I also built it the way I would build a product at work: clear problem statement, deliberate scope decisions, documented tradeoffs, known technical debt, and a human in the loop at every high-stakes decision point.

The system is not perfect. The remote column is unreliable for Apify sources. The sheet schema has fragile hardcoded column letters. VC portfolio jobs score on title only because the actor returns no descriptions.

But it runs. It finds jobs I would have missed. It scores them against criteria I actually care about. And it took me from 2-3 hours of manual job searching per day to 10 minutes of reviewing a scored sheet.

That is what shipping looks like.

---

*Stack: Python, Claude API (Sonnet 4.6), Google Sheets API, JSearch (RapidAPI), Apify, Greenhouse public API, GitHub Actions.*
*Repo: github.com/jjay05/job-hunt-os*
