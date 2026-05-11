#!/usr/bin/env python3
"""
Exploration pass — runs a sample of jobs through the local LLM with a loose
prompt to discover natural patterns before locking down the classification schema.

Company summaries are pre-loaded from data/companies_classified.json so the
LLM only handles job-specific fields. Run classify_companies.py first.

Results stream to data/explore_results.jsonl as we go.

Usage:
    python explore.py          # 50 jobs (default)
    python explore.py 200      # custom sample size
"""

import json
import random
import sys
from pathlib import Path

import ollama

DATA_FILE = Path("data/jobs_raw.json")
COMPANIES_FILE = Path("data/companies_classified.json")
OUTPUT_FILE = Path("data/explore_results.jsonl")
MODEL = "qwen3:14b"
DEFAULT_SAMPLE = 50

PROMPT = """/no_think
You are analyzing a software engineering job posting for a curated job board.

Company: {company}
Company summary: {company_summary}
Title: {title}
Location: {location}
Department: {department}

Job description:
{description}

Answer each item. Be concise — no padding, no restating the question.

1. ENGINEERING ROLE? yes / no / unclear
   Include: all levels of software engineering, SRE/DevOps, data engineering, ML/AI engineering, engineering management.
   Exclude: solutions engineers, sales engineers, IT support, DevRel, technical recruiters, product managers.

2. ROLE TYPE (if engineering):
   frontend / backend / fullstack / mobile-ios / mobile-android / mobile-cross-platform /
   data-engineering / ml-ai / infrastructure / platform / devops-sre / security / qa /
   embedded / game / engineering-management / other
   Add a brief clarifier after the type (e.g. "backend — payments API").

3. SENIORITY: intern / junior / mid / senior / staff / principal / manager / director / unclear
   Infer from the full description — years of experience, scope, mentorship expectations,
   team leadership — not just the title.

4. JOB SUMMARY (1-2 sentences): What will this person actually build or own day-to-day?
   Ignore perks, culture, and company background.

5. MUST-HAVE SKILLS: Only skills the posting explicitly marks as required, minimum
   qualifications, or "you must have". Do NOT include skills that are merely mentioned,
   preferred, or listed under "nice to have". If you are unsure, put it in nice-to-have.

6. NICE-TO-HAVE SKILLS: Skills listed as preferred, a bonus, or "nice to have".

7. OTHER SIGNALS (optional): Only include if notable — remote policy, visa sponsorship,
   salary range, equity, early-stage signals, red flags. Skip this entirely if nothing stands out.
"""


def load_company_summaries() -> dict[str, str]:
    if not COMPANIES_FILE.exists():
        return {}
    companies = json.loads(COMPANIES_FILE.read_text())
    return {c["slug"]: c.get("summary", "") for c in companies}


def load_sample(jobs: list[dict], n: int) -> list[dict]:
    with_desc = [j for j in jobs if j.get("raw_text", "").strip()]
    return random.sample(with_desc, min(n, len(with_desc)))


def explore_one(job: dict, company_summary: str) -> dict:
    description = (job.get("raw_text") or "").strip()[:4000]

    prompt = PROMPT.format(
        company=job["company"],
        company_summary=company_summary or "Unknown — infer from job description if possible.",
        title=job["title"],
        location=job.get("location") or "not specified",
        department=", ".join(job.get("departments") or []) or "not specified",
        description=description,
    )

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    return {
        "job_id": job["id"],
        "company": job["company"],
        "company_slug": job["company_slug"],
        "title": job["title"],
        "source": job["source"],
        "response": response["message"]["content"],
    }


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE
    jobs = json.loads(DATA_FILE.read_text())
    company_summaries = load_company_summaries()

    if not company_summaries:
        print("Warning: no company classifications found. Run classify_companies.py first.")

    sample = load_sample(jobs, n)
    print(f"Exploring {len(sample)} jobs (description-only) with {MODEL}")
    print()

    OUTPUT_FILE.unlink(missing_ok=True)

    for i, job in enumerate(sample, 1):
        label = f"{job['company']}: {job['title']}"
        print(f"  [{i:>3}/{len(sample)}] {label[:70]}", end=" ", flush=True)
        try:
            summary = company_summaries.get(job["company_slug"], "")
            result = explore_one(job, summary)
            with OUTPUT_FILE.open("a") as f:
                f.write(json.dumps(result) + "\n")
            print("done")
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nWritten to {OUTPUT_FILE}")
    print("\nSample outputs (first 3):")
    print("=" * 70)
    results = [json.loads(l) for l in OUTPUT_FILE.read_text().splitlines()]
    for r in results[:3]:
        print(f"\n{r['company']}: {r['title']}")
        print("-" * 50)
        print(r["response"])


if __name__ == "__main__":
    main()
