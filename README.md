# Builder Jobs — Scraper

Hourly pipeline that scrapes engineering job listings directly from company career pages, runs Claude Haiku 4.5 inference to classify and summarize each role, and publishes the results as rendered markdown to **[zachproffitt/builder-jobs](https://github.com/zachproffitt/builder-jobs)**.

## How it works

```
pipeline/fetch_jobs.py              fetch current listings from 328 companies
pipeline/fetch_job_descriptions.py  fetch full description text for new jobs
pipeline/classify_companies.py      generate company summaries via Claude Haiku 4.5
pipeline/classify_jobs.py           classify roles, summarize, extract skills and comp
pipeline/render_jobs.py             write one .md per engineering job → builder-jobs/jobs/
pipeline/generate_index.py          regenerate README.md in builder-jobs
```

The pipeline runs hourly via GitHub Actions and commits changes to both repos automatically.

## Classification

Each job is sent to Claude Haiku 4.5 with a structured prompt that extracts:

- **BUILDER** — is this a role where the person primarily writes code?
- **SUMMARY** — 1–2 sentence description in imperative voice
- **SKILLS** — up to 8 specific technologies, languages, or tools
- **LEVEL** — intern / junior / mid / senior / staff / principal / manager
- **COMP** — base salary range with original currency symbol
- **HYBRID / CONTRACT** — work arrangement flags

Only roles classified as builder engineering are rendered to the board. Contract roles are filtered out.

## Supported ATS

| ATS | Scraper |
|---|---|
| Greenhouse | `scrapers/ats_greenhouse.py` |
| Lever | `scrapers/ats_lever.py` |
| Ashby | `scrapers/ats_ashby.py` |
| SmartRecruiters | `scrapers/ats_smartrecruiters.py` |

## Rolling window

Jobs first seen more than **14 days** ago are dropped from the board and their `.md` files deleted. `seen_jobs.json` is a permanent registry of every job ID ever seen with its original `first_seen` timestamp — this prevents a long-running posting that ages out from being re-classified as new when it reappears.

New companies are archived on first fetch to avoid flooding the board with a large initial batch. Only postings that appear on subsequent runs are surfaced as new.

## Setup

Requires Python 3.11+. Clone both repos as siblings:

```bash
git clone https://github.com/zachproffitt/builder-jobs-scraper
git clone https://github.com/zachproffitt/builder-jobs
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=...
```

Run the full pipeline:

```bash
./pipeline.sh
```

Or individual steps from the repo root:

```bash
PYTHONPATH=. python pipeline/fetch_jobs.py
PYTHONPATH=. python pipeline/fetch_job_descriptions.py
PYTHONPATH=. python pipeline/classify_companies.py
PYTHONPATH=. python pipeline/classify_jobs.py
PYTHONPATH=. python pipeline/render_jobs.py ../jobs/jobs
PYTHONPATH=. python pipeline/generate_index.py ../jobs
```

## Data files

| File | Description |
|---|---|
| `data/companies.json` | 328 companies: name, ATS, slug, website |
| `data/seen_jobs.json` | Permanent ID registry: `{job_id: first_seen_date}` |
| `data/seen_companies.json` | First-fetch registry per company |
| `data/jobs_raw.json` | Rolling 14-day window of listings with descriptions |
| `data/jobs_classified.json` | Claude inference results per job ID |
| `data/companies_classified.json` | Company summaries used in rendered output |
| `data/pipeline.log` | Error log across all pipeline steps |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `claude` | `claude` or `ollama` for local inference |
| `WINDOW_DAYS` | `14` | Rolling window in days |
| `WORKERS` | `5` | Concurrent Claude API requests during classification |
