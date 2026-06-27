# Job Hunt OS: Builder Story & Learnings
*Written by Juhi Jain, AI PM building in public*

---

## Why I Built This

I was five weeks into a job search and spending 2-3 hours a day manually checking LinkedIn, Indeed, and Wellfound for PM roles. I was copying job descriptions into documents, scoring them in my head, writing cover letters from scratch, and tracking everything in a messy spreadsheet I kept forgetting to update.

I am a product manager who spent years building AI automation systems for other people's workflows. The irony of doing my own job search manually was not lost on me.

So I built the Job Hunt OS: an agentic pipeline that finds jobs across multiple sources, scores them against my actual criteria, and surfaces the best ones to me so I can focus on what only I can do: decide, reach out, and apply.

This is the story of how I built it, what I got wrong, what I learned, and what I would do differently.

---

## What I Built

A sequential skill pipeline with one human gate:

**Skill 1: Job Discovery**
Pulls PM roles from four sources on demand:
- JSearch (RapidAPI): aggregates LinkedIn, Indeed, ZipRecruiter, Glassdoor via Google for Jobs
- Apify VC Portfolio Jobs: a16z, Sequoia, YC, Greylock, and 6 more VC portfolio job boards
- Apify Wellfound Scraper: startup and AI-first company job listings

Raw results flow through a pre-filter (PM title keywords only), get deduplicated by job_id, and land in a Google Sheet.

**Skill 2a: LLM Match Scorer**
Reads each new job row, sends the full JD plus both my resumes to Claude using a 9-point rubric across four dimensions: domain match, AI readiness, skills match, and level/scope. Returns a score, tier, track (AI/ADTECH/DUAL/LOW MATCH), and a reason. Writes back to the sheet. Hard skips fire automatically for roles with coding requirements, sales roles, or agency models.

**Human Gate**
I review the sheet, read the scores and reasons, set status flags manually. Nothing gets applied without my eyes on it.

**Skill 2b, 3, 4: Deliberately paused**
Tailoring, referral lookup, and auto-apply are scoped but not built. This was a product decision, not a gap.

---

## The Decisions That Shaped This

### Cast wide, filter via scoring. Not the other way around.

My first instinct was to make the search queries specific: "AI Product Manager Seattle" or "Agentic PM Remote." That returned near-zero results because job titles don't match search strings that precisely.

The right design: broad queries (just "Senior Product Manager"), pull everything, let the scorer filter by fit. The pre-filter handles obvious noise (Director of Construction, Food Service Director). The scorer handles the rest.

This is a principle I now apply everywhere: permissive at ingestion, discriminating at evaluation.

### Sequential skills over multi-agent architecture.

I deliberately chose a linear pipeline over a multi-agent setup. One script per skill, each reading from and writing to the same Google Sheet. No agent orchestration framework, no complex handoffs.

Why: simpler to debug, easier to explain, faster to ship. When Skill 1 breaks, I know exactly where to look. When the scorer misbehaves, I can read the prompt directly. Transparency over sophistication.

For a solo-built portfolio project, clarity is the right architecture choice.

### The sheet is a permanent ledger, not a cache.

I almost made a serious mistake: the original `job_search.py` called `sheets.clear_data_rows(sheet)` on every run. Every run would have wiped my entire tracker including manual status updates I'd made (applied, interviewing, skipped).

Caught it before it caused damage. Fixed to append-only: read existing job_ids from column A, skip duplicates, only write genuinely new rows. The sheet grows forward, never resets.

Lesson: in any system where humans and automation share a data store, the automation must never overwrite human inputs.

### Manual tailoring was the right MVP decision.

I designed auto-tailoring (resume rewriting, cover letter generation, PDF creation, Drive upload) but then stopped and asked: how often will I actually apply to 40 jobs in a run? The honest answer: 3-5 per week, seriously.

Auto-tailoring 40 jobs before I've even reviewed the scores is backwards. Score first, decide which ones deserve effort, tailor manually for the ones that matter. Pasting a JD and getting a tailored cover letter in 10 minutes is faster, cheaper, and keeps me in control of every word that goes out under my name.

This is how I think about human-in-the-loop design: put the gate where the stakes are highest, not where it's easiest to automate.

### Full JD in, not truncated JD.

The scorer was silently truncating job descriptions to 3000 characters before sending them to Claude. The truncation didn't live in the discovery layer where I expected it. It lived in `build_prompt` inside the scorer, a different file written in a different session.

The result: scoring based on 750 words of a 1500-word JD. Years of experience requirements, domain signals, and specific skill callouts lived in the bottom half of most JDs. The scorer was missing all of it.

Fix: removed the cap, now sends up to 8000 characters. Cost increase: ~$0.75 per full run of 200 jobs. Worth every cent.

Lesson: always trace data from source to consumption across every file it touches. A bug that lives between two files written in different sessions is the hardest kind to find.

---

## Technical Learnings

### Adding a column is not just a schema change.

When I added a "remote" column between "location" and "salary_text", it shifted every downstream column letter. `batch_write_scores` in `sheets.py` had hardcoded ranges (I, N, O, P) that all silently broke.

This is a known Google Sheets API antipattern. The fix is to use header-name lookups instead of hardcoded column letters. I have not done this yet. It is on the technical debt list before GitHub publish.

### Two sources, two unknowns.

Both Apify actors (Wellfound and a16z/VC) don't return a remote flag natively. I set "Unknown" as the default rather than trying to parse location strings, which are inconsistently formatted and unreliable.

This means the remote column in my sheet is only reliable for JSearch results. For startup roles from Wellfound and a16z, you have to read the job description. Known limitation, documented.

### Pre-filters grow organically and get messy.

`PM_TITLE_TERMS` was added to over multiple sessions. By the time I audited it, "product lead" had been added twice. Duplicate terms don't break anything but they signal that the filter has no owner and no documentation.

Every term in a filter list should have a comment explaining what it catches and when it was added. This is not precious engineering, it's maintainability for when you come back to the code in three months.

### MCP connectors are not the same as API calls.

I assumed ZipRecruiter and Indeed had MCP connectors I could call from a Python script on a cron. They don't work that way. MCP connectors work inside Claude's runtime, not from standalone scripts running unattended.

JSearch on RapidAPI turned out to be a better solution anyway: one API key, one endpoint, aggregates LinkedIn, Indeed, ZipRecruiter, and Glassdoor simultaneously. Sometimes the right tool is simpler than what you initially designed for.

### The HN "Who's Hiring" scraper was a trap.

Apify has an actor that scrapes Hacker News monthly hiring threads. I added it thinking it would surface unique AI startup roles. What it actually returned: raw dumps of every job type with missing titles, inconsistent descriptions, and no salary data. PM roles were rare and buried.

I removed it after one run. The signal-to-noise ratio was too low to justify the maintenance cost. Sometimes the answer is: this source is not worth the complexity.

---

## What I Would Do Differently

**Start with the sheet schema.** I added columns mid-build and paid for it in downstream breakdowns. Design the full schema first, build to it. Even if columns start empty, knowing they exist prevents the hardcoded-column problem.

**Separate discovery from writing.** Right now `job_search.py` fetches and writes in one script. A cleaner design would be: fetch returns a list, a separate write function handles the sheet. Easier to test, easier to debug, easier to run either step independently.

**Write one integration test per skill.** I debugged by running the full pipeline and reading output. A test that checks "does the scorer return valid JSON with all required fields" would have caught the truncation bug in 30 seconds instead of after a full batch run.

**Document costs from day one.** I figured out the per-run cost ($1.40-$4.20 depending on JD length and job volume) late in the build. Anyone who forks this repo needs to know this upfront, not after their first surprise Anthropic bill.

---

## Running Costs (approximate)

| Component | Cost per run |
|---|---|
| JSearch API (Pro tier) | $0 (10k req/month included) |
| Apify actors (VC + Wellfound) | ~$0.10-0.20 per run |
| Claude API scoring (~200 jobs, full JD) | ~$1.40-$4.20 |
| Google Sheets API | Free |
| **Total per run** | **~$1.50-$4.50** |

At once daily: ~$45-$135/month while actively job hunting.
At 3x/week: ~$20-$60/month.

For a $200k+ job search, this math is obvious.

---

## What's Next

- Referral lookup via Apify LinkedIn actor (Skill 3)
- Digest email: daily summary of Tier 1 and Tier 2 jobs
- Evals: log every skip and edit as a feedback signal, surface scoring patterns over time
- Technical debt: replace hardcoded column letters with header-name lookups
- GitHub publish: README, system design doc, sanitized repo

---

## The Portfolio Angle

I built this because I needed it. That is the best possible reason to build something.

But I also built it the way I would build a product at work: with a clear problem statement, deliberate scope decisions, documented tradeoffs, known technical debt, and a human in the loop at every high-stakes decision point.

The system is not perfect. It has known gaps. The remote column is unreliable for Apify sources. The sheet schema has fragile hardcoded columns. Tailoring is manual.

But it runs. It finds jobs I would have missed. It scores them against criteria I actually care about. And it took me from 2-3 hours of manual job searching per day to 10 minutes of reviewing a scored sheet.

That is what shipping looks like.
