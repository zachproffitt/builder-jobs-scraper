#!/usr/bin/env python3
"""
Classify jobs as engineering or non-engineering, and generate a one-sentence
job summary for roles that have description text.

Strategy:
  - Jobs WITHOUT description: title keyword matching (fast, free, ~95% accurate)
  - Jobs WITH description: LLM classification + summary generation

Output is data/jobs_classified.json — a dict keyed by job_id with:
  {
    "is_engineering": true/false/null,  # null = couldn't determine
    "job_summary": "...",               # only when description text available
    "source_hash": "..."                # hash of input data for delta skipping
  }

Only jobs where is_engineering=true are rendered to the jobs/ output.

Usage:
    python classify_jobs.py
"""

import hashlib
import json
import re
from pathlib import Path

import ollama

JOBS_FILE = Path("data/jobs_raw.json")
OUTPUT_FILE = Path("data/jobs_classified.json")
MODEL = "qwen3:14b"

# Title keywords that reliably indicate engineering roles
ENGINEERING_TITLES = re.compile(
    r"\b(software|engineer|developer|dev|sre|devops|dev ops|architect|"
    r"backend|front.?end|full.?stack|mobile|ios|android|"
    r"infrastructure|platform|security|firmware|embedded|"
    r"machine learning|ml |data engineer|ai engineer|"
    r"qa |quality assurance|test engineer|site reliability|"
    r"kernel|systems programmer|engineering manager)\b",
    re.I,
)

# Title keywords that reliably indicate non-engineering roles
NON_ENGINEERING_TITLES = re.compile(
    r"\b(sales|account executive|account manager|marketing|"
    r"recruiter|recruiting|talent|hr |human resources|"
    r"finance|counsel|legal|paralegal|"
    r"product manager|\bpm\b|program manager|"
    r"designer|ux |ui |illustrat|"
    r"copywriter|content|social media|"
    r"solutions engineer|sales engineer|"
    r"customer success|customer support|support engineer|"
    r"business development|biz dev|partnerships|"
    r"operations manager|office manager|executive assistant|"
    r"data analyst|business analyst|financial analyst)\b",
    re.I,
)

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


def classify_by_title(title: str) -> bool | None:
    if NON_ENGINEERING_TITLES.search(title):
        return False
    if ENGINEERING_TITLES.search(title):
        return True
    return None  # ambiguous — would need description to decide


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

    to_process = [
        j for j in jobs
        if j["id"] not in existing
        or existing[j["id"]].get("source_hash") != source_hash(j)
    ]

    print(f"{len(to_process)} jobs to classify ({len(existing)} cached, {len(jobs)} total)\n")

    with_desc = [j for j in to_process if j.get("raw_text", "").strip()]
    without_desc = [j for j in to_process if not j.get("raw_text", "").strip()]

    # Title-only pass (fast)
    print(f"Title matching: {len(without_desc)} jobs...")
    title_eng = title_not_eng = title_unclear = 0
    for job in without_desc:
        result = classify_by_title(job["title"])
        if result is True:
            title_eng += 1
        elif result is False:
            title_not_eng += 1
        else:
            title_unclear += 1
        existing[job["id"]] = {
            "is_engineering": result,
            "job_summary": None,
            "source_hash": source_hash(job),
        }
    print(f"  engineering: {title_eng}, not: {title_not_eng}, unclear: {title_unclear}\n")

    # LLM pass (description text available)
    if with_desc:
        print(f"LLM classification: {len(with_desc)} jobs with descriptions...")
        llm_eng = llm_not_eng = llm_unclear = llm_errors = 0
        for i, job in enumerate(with_desc, 1):
            label = f"{job['company']}: {job['title'][:50]}"
            print(f"  [{i:>3}/{len(with_desc)}] {label}", end=" ", flush=True)
            try:
                is_eng, summary = classify_with_llm(job)
                existing[job["id"]] = {
                    "is_engineering": is_eng,
                    "job_summary": summary,
                    "source_hash": source_hash(job),
                }
                if is_eng is True:
                    llm_eng += 1
                    print(f"✓ {(summary or 'no summary')[:60]}")
                elif is_eng is False:
                    llm_not_eng += 1
                    print("✗ not engineering")
                else:
                    llm_unclear += 1
                    print("? unclear")
            except Exception as e:
                llm_errors += 1
                print(f"ERROR: {e}")

        print(f"\n  engineering: {llm_eng}, not: {llm_not_eng}, unclear: {llm_unclear}, errors: {llm_errors}")

    OUTPUT_FILE.write_text(json.dumps(existing, indent=2))
    total_eng = sum(1 for v in existing.values() if v.get("is_engineering") is True)
    print(f"\nWritten to {OUTPUT_FILE}")
    print(f"Total engineering roles: {total_eng}/{len(existing)}")


if __name__ == "__main__":
    main()
