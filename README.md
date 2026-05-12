# builder-jobs-scraper

Pipeline that scrapes engineering jobs from company career pages, classifies them with an LLM, and publishes rendered markdown to [zachproffitt/builder-jobs](https://github.com/zachproffitt/builder-jobs).

Only roles where the person will primarily write code or build systems are included — no sales engineers, TPMs, analysts, or other engineering-adjacent titles.

## Supported ATS

| ATS | Listing API | Descriptions | Posted date |
|---|---|---|---|
| Greenhouse | ✓ | Fetched separately | ✗ |
| Lever | ✓ | Included in listing | ✓ |
| Ashby | ✓ | Included in listing | ✓ |

## Adding a company

**1. Find the company's ATS slug.**

Check their careers page URL. The slug is the company identifier in the ATS URL:

- Greenhouse: `https://boards.greenhouse.io/{slug}` or `https://job-boards.greenhouse.io/{slug}`
- Lever: `https://jobs.lever.co/{slug}`
- Ashby: `https://jobs.ashbyhq.com/{slug}`

Or use `discover_companies.py` to auto-detect it from the company's website:

```
echo "Acme Corp | acme.com" >> data/company_names.txt
python discover_companies.py
```

**2. Add to `data/companies.json`:**

```json
{
  "name": "Acme Corp",
  "ats": "greenhouse",
  "slug": "acme",
  "website": "https://acme.com"
}
```

That's it. The company will be picked up on the next pipeline run.

## Pipeline

Run these steps in order. Each step is independent and checkpointed — you can stop and resume.

```
python fetch_jobs.py          # fetch job listings from all companies
python fetch_descriptions.py  # fetch full description text (Greenhouse only)
python classify_jobs.py       # LLM classification: builder vs. not
python render.py              # write markdown files to jobs/
python generate_index.py      # regenerate README.md in the jobs repo
```

## Setup

```
pip install -r requirements.txt
```

Classification requires [Ollama](https://ollama.com) running locally with `qwen3:14b`:

```
ollama pull qwen3:14b
```

For faster classification at scale, set `CLASSIFIER=gemini` or `CLASSIFIER=groq` (requires API keys — not yet implemented, planned for GitHub Actions).

## Data files

| File | Description |
|---|---|
| `data/companies.json` | Company list with ATS and slug |
| `data/jobs_raw.json` | Raw job listings with descriptions |
| `data/jobs_classified.json` | Classification results per job ID |
| `data/companies_classified.json` | Company summaries for rendered output |

## Output

Rendered job files are written to `jobs/` in the working directory by default. `generate_index.py` defaults to `../builder-jobs` (the sibling repo) and accepts an optional path argument:

```
python generate_index.py /path/to/builder-jobs
```
