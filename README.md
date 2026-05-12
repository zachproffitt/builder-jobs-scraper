# builder-jobs-scraper

Pipeline that fetches engineering job listings directly from company career pages, classifies them with a local LLM, and publishes rendered markdown to **[zachproffitt/builder-jobs](https://github.com/zachproffitt/builder-jobs)**.

## How it works

Jobs are fetched from each company's career page, classified by a local LLM (builder role or not), and rendered as markdown files.

```
fetch_jobs.py              fetch current listings from all companies
fetch_job_descriptions.py  fetch full description text (where not included in listing)
classify_jobs.py           LLM: is this a builder role? summarize, extract skills
render_jobs.py             write one .md per engineering job → builder-jobs/jobs/
generate_index.py          regenerate README.md in builder-jobs
```

Run the full pipeline:

```bash
make run
```

Or run individual steps:

```bash
make fetch
make describe
make classify
make render
make index
```

## Supported ATS

| ATS | Supported | Scraper |
|---|---|---|
| Greenhouse | ✓ | `scrapers/ats_greenhouse.py` |
| Lever | ✓ | `scrapers/ats_lever.py` |
| Ashby | ✓ | `scrapers/ats_ashby.py` |
| SmartRecruiters | ✓ | `scrapers/ats_smartrecruiters.py` |
| Rippling | planned | — |
| Workday | planned | — |

## Adding companies

Add any company to `data/company_names.txt` in the format `Company Name | domain.com`:

```
Acme Corp | acme.com
```

Then run:

```bash
make discover
```

`discover_companies.py` visits the company's careers page, detects the ATS, and extracts the slug automatically. Results are written to `data/companies.json`. If a slug is detected incorrectly, edit `companies.json` directly — that entry is skipped on future discover runs.

## Rolling window

Only jobs first seen within the last **14 days** are kept. On each run, older jobs are dropped from `jobs_raw.json` and their rendered `.md` files are deleted from `builder-jobs`.

`seen_jobs.json` is a permanent registry of every job ID ever seen with its original `first_seen` date. This prevents a long-running posting that ages out of the window from being re-classified as new when it re-appears.

Each daily run only classifies jobs where `first_seen = today` (new arrivals) or where a job's content has changed since last classification. Use `--all` flags on the first run or after a gap.

## Setup

Requires Python 3.11+. Clone both repos as siblings:

```bash
git clone https://github.com/zachproffitt/builder-jobs-scraper
git clone https://github.com/zachproffitt/builder-jobs
```

The two repos must be siblings on disk — `render_jobs.py` and `generate_index.py` default to writing output to `../jobs/`.

Install dependencies:

```bash
pip install -r requirements.txt
```

Install [Ollama](https://ollama.com) and pull the classification model:

```bash
ollama pull qwen3:14b
```

## First run

On the first run, use `--all` flags to fetch descriptions and classify the full current set of listings rather than just today's new ones:

```bash
make fetch
make describe-all
make classify-all
make render
make index
```

After that, `make run` handles everything daily.

## Data files

| File | Description |
|---|---|
| `data/company_names.txt` | Input list: `Company Name \| domain.com` |
| `data/companies.json` | Resolved companies: name, ATS, slug |
| `data/seen_jobs.json` | Permanent ID registry: `{job_id: first_seen_date}` |
| `data/jobs_raw.json` | Rolling 14-day window of listings with descriptions |
| `data/jobs_classified.json` | LLM results per job ID |
| `data/companies_classified.json` | Company summaries used in rendered output |

## Configuration

| Parameter | File | Default | Description |
|---|---|---|---|
| `WINDOW_DAYS` | `fetch_jobs.py` | `14` | Rolling window in days |
| `MODEL` | `classify_jobs.py` | `qwen3:14b` | Ollama model |
| `WORKERS` | `classify_jobs.py` | `3` | Concurrent LLM requests |
| `WORKERS` | `fetch_job_descriptions.py` | `10` | Concurrent description fetches |
| `SAVE_EVERY` | `classify_jobs.py` | `100` | Checkpoint interval (jobs between saves) |

## Known issues

- ~27 companies in `companies.json` have incorrect slugs and return 404 errors on every run. These need to be corrected or removed.
