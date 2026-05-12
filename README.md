# builder-jobs-scraper

Pipeline that pulls engineering job listings directly from company ATS APIs and publishes them to [zachproffitt/builder-jobs](https://github.com/zachproffitt/builder-jobs).

Rather than scraping aggregator job boards like LinkedIn or Indeed, we pull directly from each company's ATS — giving fresher data and avoiding the noise of reposted or sponsored listings.

## How it works

Jobs are fetched from each company's ATS, classified by a local LLM (builder role or not), and rendered as markdown files in a separate output repo. The output repo is kept clean and browsable on its own — no pipeline code, just jobs.

```
fetch_jobs.py           fetch current listings from all companies
fetch_descriptions.py   fetch full description text (where not in listing API)
classify_jobs.py        LLM: is this a builder role? summarize, extract skills
render.py               write one .md per engineering job → builder-jobs/jobs/
generate_index.py       regenerate README.md in builder-jobs
```

Run all steps in sequence:

```bash
make run
```

Or run individual steps:

```bash
make fetch
make describe
make classify
make render
```

## Supported ATS

| ATS | Descriptions in listing |
|---|---|
| Greenhouse | ✗ |
| Lever | ✓ |
| Ashby | ✓ |
| SmartRecruiters | ✓ |
| Rippling | in progress |

## Adding companies

Add any company to `data/company_names.txt` in the format `Company Name | domain.com`:

```
Acme Corp | acme.com
```

Then run:

```bash
make discover
```

`discover_companies.py` will visit the company's careers page, detect the ATS, and extract the slug automatically. Results are written to `data/companies.json`. If a slug is wrong, edit `companies.json` directly — that entry is skipped on future runs.

## Rolling window

Only jobs first seen within the last **14 days** are kept. Older jobs are dropped from `jobs_raw.json` and their rendered `.md` files are deleted from `builder-jobs` on each run.

`seen_jobs.json` is a permanent registry of every job ID ever seen with its original `first_seen` date. This ensures a long-running posting that ages out of the window and re-appears on the ATS keeps its original date and is not re-classified as new.

Each daily run only classifies jobs where `first_seen = today` (new arrivals) or where job content has changed since the last classification.

## Setup

Clone both repos as siblings:

```bash
git clone https://github.com/zachproffitt/builder-jobs-scraper
git clone https://github.com/zachproffitt/builder-jobs
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install [Ollama](https://ollama.com) and pull the classification model:

```bash
ollama pull qwen3:14b
```

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
| `WORKERS` | `fetch_descriptions.py` | `10` | Concurrent description fetches |
| `SAVE_EVERY` | `classify_jobs.py` | `100` | Checkpoint interval |

## Known issues

- ~27 companies in `companies.json` have incorrect slugs and return 404 errors every run. These need to be corrected or removed.
