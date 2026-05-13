#!/usr/bin/env python3
"""Classify jobs as builder engineering roles and generate summaries."""

import hashlib
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import ollama

JOBS_FILE = Path(__file__).parent.parent / "data" / "jobs_raw.json"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "jobs_classified.json"
MODEL = "qwen3:8b"
WORKERS = 2  # concurrent Ollama requests
SAVE_EVERY = 100

PROMPT = """/no_think
You are filtering a job board for software engineers — people who primarily write code.

INCLUDE — person primarily writes code:
- Software engineers of all kinds (backend, frontend, mobile, infrastructure, platform, SRE, DevOps)
- Data engineers building pipelines, ETL systems, data infrastructure
- ML/AI engineers building models, training infrastructure, inference systems
- Security engineers building security systems and tooling
- QA/test engineers writing automation and test infrastructure
- Firmware and embedded software engineers (writing code that runs on hardware)
- Kernel and systems software engineers
- Engineering managers leading teams of software engineers
- Researchers who primarily build novel models or software systems (e.g., at AI/ML labs)
- Data scientists who primarily build and train models, not just analyze data
- Analytics engineers building data pipelines and warehouse infrastructure
- Forward deployed engineers embedded at client sites writing and deploying software

EXCLUDE — person is not primarily writing code:
- Sales, marketing, HR, recruiting, finance, legal, operations
- Solutions engineers and sales engineers (customer-facing, not building)
- Technical program managers (coordinating, not coding)
- Developer advocates and developer relations
- Product managers and product designers
- Hardware engineers (electrical, mechanical, PCB design, RF, optical, systems integration of physical components)
- Manufacturing, process, and production engineers
- Any title containing "analyst" without also containing "engineer" — data analyst,
  business analyst, product analyst, operations analyst, marketing analyst, etc.
  (Analytics Engineer and Data Engineer stay in; Data Analyst is out)
- Research roles that are primarily analytical rather than building software systems

For borderline cases where the title doesn't resolve it, use the description:
ask "Will this person primarily write code?" — if yes, BUILDER; if no or unclear, exclude.
A firmware engineer writes code. A hardware engineer designs circuits or physical components — exclude them.
An electrical engineer working on subsystems, power, or manufacturing is a hardware engineer — exclude them.
A "Technical Mission Designer" or "Technical Designer" in game dev is a designer who uses scripts — exclude them.
A "Technical Animator" is borderline — include only if the description is primarily about building animation systems in code.

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
   Comma-separated. Be specific — "PyTorch" not "ML", "Rust" not "systems programming", "JavaScript" not "JS",
   "Unreal Engine" not "UE" or "UR", "PostgreSQL" not "databases".
   Avoid generic terms like "backend", "frontend", "cloud", "APIs" — name the actual technology.
   If none are clearly mentioned, write: n/a

4. LEVEL: Seniority of this role. Use signals in this priority order:
   a. Title keyword (most reliable):
      "Intern"/"Co-op" → intern
      "Junior"/"Associate"/"Entry" → junior
      "Senior" → senior
      "Staff" → staff
      "Principal" → principal
      "Manager"/"Director" → manager
      No keyword → use years of experience from description
   b. Years of experience in description:
      0-1 → junior, 1-3 → mid, 3-6 → senior, 6-10 → staff, 10+ → principal
   c. If title has a level keyword, use it even if description says fewer years.
   d. If no signal at all, write: unclear

   Respond with exactly one of: intern / junior / mid / senior / staff / principal / manager / unclear

5. CONTRACT: Is this a contract, temporary, or fixed-term position rather than permanent full-time employment?
   yes = contract, contractor, freelance, fixed-term, temporary, limited-term engagement
   no = permanent full-time employment (default if not stated)
   Look for signals in the title (e.g. "CONTRACT", "Contractor") and description (e.g. "12-month contract",
   "fixed-term", "temporary position"). Ignore uses of "contract" that refer to the domain or work content
   (e.g. "smart contracts", "government contracts", "contract negotiation").

   Respond with exactly one of: yes / no

Respond in exactly this format:
BUILDER: <yes/no/unclear>
SUMMARY: <summary or vague or n/a>
SKILLS: <skill1, skill2, ... or n/a>
LEVEL: <intern/junior/mid/senior/staff/principal/manager/unclear>
CONTRACT: <yes/no>
"""


def content_hash(job: dict) -> str:
    key = f"{job['id']}:{job['title']}:{job.get('raw_text', '')[:200]}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


VALID_LEVELS = {"intern", "junior", "mid", "senior", "staff", "principal", "manager"}


def classify_with_llm(job: dict) -> tuple[bool | None, str | None, list[str], str | None, bool]:
    description = job.get("raw_text", "").strip()[:3000]
    prompt = PROMPT.format(
        title=job["title"],
        company=job["company"],
        description=description,
    )
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1, "num_ctx": 4096},
        keep_alive="10m",
    )
    text = response["message"]["content"].strip()

    is_engineering = None
    job_summary = None
    skills = []
    level = None
    is_contract = False

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
                skills = [s.strip() for s in re.split(r",\s*(?![^(]*\))", val) if s.strip()]
        elif line.startswith("LEVEL:"):
            val = line.removeprefix("LEVEL:").strip().lower()
            if val in VALID_LEVELS:
                level = val
        elif line.startswith("CONTRACT:"):
            val = line.removeprefix("CONTRACT:").strip().lower()
            is_contract = val == "yes"

    return is_engineering, job_summary, skills, level, is_contract


def main():
    jobs = json.loads(JOBS_FILE.read_text())

    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text())

    classify_all = "--all" in sys.argv
    today = datetime.now(timezone.utc).date().isoformat()

    def needs_work(j: dict) -> bool:
        ex = existing.get(j["id"])
        if ex and ex.get("source_hash") == content_hash(j) and not classify_all:
            return False
        return (
            classify_all
            or j.get("first_seen") == today
            or j["id"] in existing
        )

    with_desc = [
        j for j in jobs
        if j.get("raw_text", "").strip() and needs_work(j)
    ]
    without_desc = sum(1 for j in jobs if not j.get("raw_text", "").strip())

    print(f"{len(with_desc)} jobs to classify today, {without_desc} skipped (no description)")
    print(f"Workers: {WORKERS}, Model: {MODEL}\n")

    if not with_desc:
        print("Nothing to classify. Run fetch_job_descriptions.py first if Greenhouse jobs are missing descriptions.")
        return

    eng = not_eng = unclear = errors = 0
    lock = threading.Lock()
    completed = 0
    total = len(with_desc)

    def process(job: dict) -> tuple:
        return job, classify_with_llm(job)

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_job = {executor.submit(process, job): job for job in with_desc}

        for future in as_completed(future_to_job):
            with lock:
                completed += 1
                n = completed

            try:
                job, (is_e, summary, skills, level, is_contract) = future.result()
            except Exception as e:
                job = future_to_job[future]
                with lock:
                    errors += 1
                print(f"  [{n:>5}/{total}] ERROR {job['company']}: {job['title'][:50]} — {e}")
                continue

            with lock:
                existing[job["id"]] = {
                    "is_engineering": is_e,
                    "is_contract": is_contract,
                    "job_summary": summary,
                    "skills": skills,
                    "level": level,
                    "source_hash": content_hash(job),
                }
                if is_e is True:
                    eng += 1
                    contract_tag = " [contract]" if is_contract else ""
                    line = f"  [{n:>5}/{total}] ✓ {job['company']}: {job['title'][:50]}{contract_tag} — {(summary or 'no summary')[:60]}"
                elif is_e is False:
                    not_eng += 1
                    line = f"  [{n:>5}/{total}] ✗ {job['company']}: {job['title'][:50]}"
                else:
                    unclear += 1
                    line = f"  [{n:>5}/{total}] ? {job['company']}: {job['title'][:50]}"

                print(line)

                if n % SAVE_EVERY == 0:
                    OUTPUT_FILE.write_text(json.dumps(existing, indent=2))
                    print(f"  [checkpoint] saved {n}/{total}")

    OUTPUT_FILE.write_text(json.dumps(existing, indent=2))
    total_eng = sum(1 for v in existing.values() if v.get("is_engineering") is True)

    print(f"\nThis run — builder: {eng}, not: {not_eng}, unclear: {unclear}, errors: {errors}")
    print(f"Written to {OUTPUT_FILE}")
    print(f"Total builder roles in cache: {total_eng}/{len(existing)}")


if __name__ == "__main__":
    main()
