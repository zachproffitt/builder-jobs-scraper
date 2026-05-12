#!/usr/bin/env python3
"""
Classify jobs as builder engineering roles and generate one-sentence summaries.
Classification is done by LLM using the full job description.

Jobs without a description are skipped — run fetch_descriptions.py first to
fill in Greenhouse descriptions, then re-run this script.

Output is data/jobs_classified.json — a dict keyed by job_id with:
  {
    "is_engineering": true/false/null,  # null = no description available yet
    "job_summary": "...",               # only when is_engineering=true
    "skills": ["Python", "Rust", ...],  # only when is_engineering=true
    "source_hash": "..."                # hash of input data for delta skipping
  }

Only jobs where is_engineering=true are rendered to the jobs/ output.

Usage:
    python classify_jobs.py
"""

import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import ollama

JOBS_FILE = Path("data/jobs_raw.json")
OUTPUT_FILE = Path("data/jobs_classified.json")
LOG_FILE = Path("logs/classify_jobs.log")
MODEL = "qwen3:14b"
WORKERS = 3  # concurrent Ollama requests

PROMPT = """/no_think
You are filtering a job board for software builders — people who primarily write code or build software/hardware systems.

INCLUDE — person primarily writes code or builds systems:
- Software engineers of all kinds (backend, frontend, mobile, infrastructure, platform, SRE, DevOps)
- Data engineers building pipelines, ETL systems, data infrastructure
- ML/AI engineers building models, training infrastructure, inference systems
- Security engineers building security systems and tooling
- QA/test engineers writing automation and test infrastructure
- Firmware, embedded, kernel engineers
- Engineering managers leading teams of builders
- Researchers who primarily build novel models or systems (e.g., at AI/ML labs)
- Data scientists who primarily build and train models, not just analyze data
- Analytics engineers building data pipelines and warehouse infrastructure
- Forward deployed engineers embedded at client sites writing and deploying software

EXCLUDE — person is not primarily writing code:
- Sales, marketing, HR, recruiting, finance, legal, operations
- Solutions engineers and sales engineers (customer-facing, not building)
- Technical program managers (coordinating, not coding)
- Developer advocates and developer relations
- Product managers and product designers
- Any title containing "analyst" without also containing "engineer" — data analyst,
  business analyst, product analyst, operations analyst, marketing analyst, etc.
  (Analytics Engineer and Data Engineer stay in; Data Analyst is out)
- Research roles that are primarily analytical rather than building systems

For borderline cases where the title doesn't resolve it, use the description:
ask "Will this person primarily write code or build systems?" — if yes, BUILDER; if no or unclear, exclude.

Job title: {title}
Company: {company}

Description:
{description}

Answer both:

1. BUILDER: yes / no / unclear
   yes = will primarily write code or build systems
   no = will not primarily write code
   unclear = description doesn't make it possible to determine

2. SUMMARY (only if BUILDER is yes): 1-2 sentences in imperative active voice starting with a verb.
   E.g. "Build and maintain the data pipeline..." or "Own the compiler backend..."
   Name the specific system, product, or infrastructure. No perks, no culture.
   If too vague to summarize honestly, write: vague

3. SKILLS (only if BUILDER is yes): up to 5 specific technologies, languages, or tools mentioned in the description.
   Comma-separated. Be specific — "PyTorch" not "ML", "Rust" not "systems programming".
   If none are clearly mentioned, write: n/a

Respond in exactly this format:
BUILDER: <yes/no/unclear>
SUMMARY: <summary or vague or n/a>
SKILLS: <skill1, skill2, ... or n/a>
"""


def source_hash(job: dict) -> str:
    key = f"{job['id']}:{job['title']}:{job.get('raw_text', '')[:200]}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def classify_with_llm(job: dict) -> tuple:
    """Returns (is_engineering, job_summary, skills)."""
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
    skills = []

    for line in text.splitlines():
        if line.startswith("BUILDER:"):
            val = line.removeprefix("BUILDER:").strip().lower()
            if val == "yes":
                is_engineering = True
            elif val == "no":
                is_engineering = False
        elif line.startswith("SUMMARY:"):
            val = line.removeprefix("SUMMARY:").strip()
            if val.lower() not in ("n/a", "vague", ""):
                job_summary = val
        elif line.startswith("SKILLS:"):
            val = line.removeprefix("SKILLS:").strip()
            if val.lower() != "n/a":
                skills = [s.strip() for s in val.split(",") if s.strip()]

    return is_engineering, job_summary, skills


def main():
    LOG_FILE.parent.mkdir(exist_ok=True)
    log = open(LOG_FILE, "a", buffering=1)

    def emit(msg: str):
        print(msg)
        log.write(msg + "\n")

    jobs = json.loads(JOBS_FILE.read_text())

    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text())

    classify_all = "--all" in sys.argv
    today = date.today().isoformat()

    def needs_work(j: dict) -> bool:
        # Skip if already classified with the same content
        ex = existing.get(j["id"])
        if ex and ex.get("source_hash") == source_hash(j):
            return False
        # Include if: new today, content changed on known job, or --all
        return (
            classify_all
            or j.get("first_seen") == today
            or j["id"] in existing  # content changed (hash already differs from above)
        )

    with_desc = [
        j for j in jobs
        if j.get("raw_text", "").strip() and needs_work(j)
    ]
    without_desc = sum(1 for j in jobs if not j.get("raw_text", "").strip())

    emit(f"{len(with_desc)} jobs to classify today, {without_desc} skipped (no description)")
    emit(f"Workers: {WORKERS}, Model: {MODEL}\n")

    if not with_desc:
        emit("Nothing to classify. Run fetch_descriptions.py first if Greenhouse jobs are missing descriptions.")
        log.close()
        return

    eng = not_eng = unclear = errors = 0
    lock = threading.Lock()
    completed = 0
    total = len(with_desc)

    # Periodically flush results to disk so progress survives interruption
    SAVE_EVERY = 100

    def process(job: dict) -> tuple:
        return job, classify_with_llm(job)  # returns (job, (is_e, summary, skills))

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_job = {executor.submit(process, job): job for job in with_desc}

        for future in as_completed(future_to_job):
            with lock:
                completed += 1
                n = completed

            try:
                job, (is_e, summary, skills) = future.result()
            except Exception as e:
                job = future_to_job[future]
                with lock:
                    errors += 1
                emit(f"  [{n:>5}/{total}] ERROR {job['company']}: {job['title'][:50]} — {e}")
                continue

            with lock:
                existing[job["id"]] = {
                    "is_engineering": is_e,
                    "job_summary": summary,
                    "skills": skills,
                    "source_hash": source_hash(job),
                }
                if is_e is True:
                    eng += 1
                    line = f"  [{n:>5}/{total}] ✓ {job['company']}: {job['title'][:50]} — {(summary or 'no summary')[:60]}"
                elif is_e is False:
                    not_eng += 1
                    line = f"  [{n:>5}/{total}] ✗ {job['company']}: {job['title'][:50]}"
                else:
                    unclear += 1
                    line = f"  [{n:>5}/{total}] ? {job['company']}: {job['title'][:50]}"

                emit(line)

                if n % SAVE_EVERY == 0:
                    OUTPUT_FILE.write_text(json.dumps(existing, indent=2))
                    emit(f"  [checkpoint] saved {n}/{total}")

    OUTPUT_FILE.write_text(json.dumps(existing, indent=2))
    total_eng = sum(1 for v in existing.values() if v.get("is_engineering") is True)

    emit(f"\nThis run — builder: {eng}, not: {not_eng}, unclear: {unclear}, errors: {errors}")
    emit(f"Written to {OUTPUT_FILE}")
    emit(f"Total builder roles in cache: {total_eng}/{len(existing)}")
    log.close()


if __name__ == "__main__":
    main()
