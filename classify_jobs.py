#!/usr/bin/env python3
"""
Classify jobs as engineering or non-engineering, and generate a one-sentence
job summary. Classification is done by LLM using the full job description.

Jobs without a description are skipped — run fetch_descriptions.py first to
fill in Greenhouse descriptions, then re-run this script.

Output is data/jobs_classified.json — a dict keyed by job_id with:
  {
    "is_engineering": true/false/null,  # null = no description available yet
    "job_summary": "...",               # only when is_engineering=true
    "source_hash": "..."                # hash of input data for delta skipping
  }

Only jobs where is_engineering=true are rendered to the jobs/ output.

Usage:
    python classify_jobs.py
"""

import hashlib
import json
from pathlib import Path

import ollama

JOBS_FILE = Path("data/jobs_raw.json")
OUTPUT_FILE = Path("data/jobs_classified.json")
MODEL = "qwen3:14b"

PROMPT = """/no_think
You are filtering a software engineering job board. Evaluate this job posting.

Job title: {title}
Company: {company}

Description:
{description}

Answer both questions:

1. ENGINEERING: yes / no / unclear
   yes = software engineering, SRE, DevOps, data engineering, ML/AI engineering, engineering management
   no = sales, marketing, HR, recruiting, finance, design, product management, solutions engineering, customer success
   unclear = genuinely ambiguous from title and description

2. SUMMARY (only if ENGINEERING is yes): 1-2 sentences. What will this person actually build or own?
   Be specific — name the system, product, or infrastructure. Ignore perks and culture.
   If the description is too vague to summarize honestly, write: vague

Respond in exactly this format:
ENGINEERING: <yes/no/unclear>
SUMMARY: <summary or vague or n/a>
"""


def source_hash(job: dict) -> str:
    key = f"{job['id']}:{job['title']}:{job.get('raw_text', '')[:200]}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def classify_with_llm(job: dict) -> tuple:
    """Returns (is_engineering, job_summary)."""
    description = job.get("raw_text", "").strip()[:3000]
    prompt = PROMPT.format(
        title=job["title"],
        company=job["company"],
        description=description,
    )
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
        keep_alive="10m",
    )
    text = response["message"]["content"].strip()

    is_engineering = None
    job_summary = None

    for line in text.splitlines():
        if line.startswith("ENGINEERING:"):
            val = line.removeprefix("ENGINEERING:").strip().lower()
            if val == "yes":
                is_engineering = True
            elif val == "no":
                is_engineering = False
        elif line.startswith("SUMMARY:"):
            val = line.removeprefix("SUMMARY:").strip()
            if val.lower() not in ("n/a", "vague", ""):
                job_summary = val

    return is_engineering, job_summary


def main():
    jobs = json.loads(JOBS_FILE.read_text())

    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text())

    with_desc = [
        j for j in jobs
        if j.get("raw_text", "").strip()
        and (
            j["id"] not in existing
            or existing[j["id"]].get("source_hash") != source_hash(j)
        )
    ]
    without_desc = sum(1 for j in jobs if not j.get("raw_text", "").strip())

    print(f"{len(with_desc)} jobs to classify, {without_desc} skipped (no description yet)\n")

    if not with_desc:
        print("Nothing to classify. Run fetch_descriptions.py first if Greenhouse jobs are missing descriptions.")
        return

    eng = not_eng = unclear = errors = 0

    for i, job in enumerate(with_desc, 1):
        label = f"{job['company']}: {job['title'][:50]}"
        print(f"  [{i:>3}/{len(with_desc)}] {label}", end=" ", flush=True)
        try:
            is_e, summary = classify_with_llm(job)
            existing[job["id"]] = {
                "is_engineering": is_e,
                "job_summary": summary,
                "source_hash": source_hash(job),
            }
            if is_e is True:
                eng += 1
                print(f"✓ {(summary or 'no summary')[:60]}")
            elif is_e is False:
                not_eng += 1
                print("✗ not engineering")
            else:
                unclear += 1
                print("? unclear")
        except Exception as e:
            errors += 1
            print(f"ERROR: {e}")

    OUTPUT_FILE.write_text(json.dumps(existing, indent=2))
    total_eng = sum(1 for v in existing.values() if v.get("is_engineering") is True)
    print(f"\nThis run — engineering: {eng}, not: {not_eng}, unclear: {unclear}, errors: {errors}")
    print(f"Written to {OUTPUT_FILE}")
    print(f"Total engineering roles in cache: {total_eng}/{len(existing)}")


if __name__ == "__main__":
    main()
