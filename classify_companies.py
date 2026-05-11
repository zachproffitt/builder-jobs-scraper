#!/usr/bin/env python3
"""
Classify companies — runs once per new company, not per job.

Reads data/companies.json, classifies any companies not already in
data/companies_classified.json, and writes results back.

Uses job description excerpts as grounding where available (Ashby/Lever jobs).
Falls back to model knowledge for companies with no descriptions (Greenhouse),
marking those results as grounded=False for review.

Usage:
    python classify_companies.py
"""

import hashlib
import json
from pathlib import Path

import ollama

COMPANIES_FILE = Path("data/companies.json")
JOBS_FILE = Path("data/jobs_raw.json")
OUTPUT_FILE = Path("data/companies_classified.json")
MODEL = "qwen3:14b"

SHARED_INSTRUCTIONS = """
Answer each item precisely:

1. SUMMARY (1 sentence max): What does this company do? Focus on the product,
   not company values or culture. Write it as a fact, not marketing copy.
   Bad: "X is a fast-growing company that empowers developers."
   Good: "X builds open-source Postgres tooling for backend developers."

2. INDUSTRY TAGS: Choose 2-4 from this list (comma-separated):
   ai-ml, fintech, payments, developer-tools, infrastructure, cloud, security,
   data, open-source, enterprise-software, consumer, ecommerce, healthcare,
   edtech, gaming, media, crypto, saas, marketplace, other

3. STAGE: Pick one — infer from team size, funding, or growth signals:
   early-stage (seed/series A, <100 employees)
   growth (series B-D, 100-1000 employees)
   late-stage (post-series D or pre-IPO, 1000+ employees)
   public (publicly traded)
   unknown

Respond in exactly this format — no extra text:
SUMMARY: <one sentence>
INDUSTRY: <tag1>, <tag2>
STAGE: <stage>
"""

PROMPT_GROUNDED = """/no_think
You are building a concise company profile for a software engineering job board.
Base your answers ONLY on the job description excerpts below — do not rely on
prior knowledge, as it may be outdated or wrong.

Company name: {name}

Job description excerpts (from {name}'s actual postings):
---
{excerpts}
---
""" + SHARED_INSTRUCTIONS

PROMPT_KNOWLEDGE = """/no_think
You are building a concise company profile for a software engineering job board.
Use your training knowledge about this well-known company.

Company name: {name}
""" + SHARED_INSTRUCTIONS


def source_hash(company: dict) -> str:
    return hashlib.md5(json.dumps(company, sort_keys=True).encode()).hexdigest()[:8]


def get_excerpts(slug: str, jobs: list[dict], n: int = 3, chars: int = 800) -> "str | None":
    matches = [j for j in jobs if j.get("company_slug") == slug and j.get("raw_text", "").strip()]
    if not matches:
        return None
    parts = []
    for job in matches[:n]:
        text = job["raw_text"].strip()[:chars]
        parts.append(f"[{job['title']}]\n{text}")
    return "\n\n".join(parts)


def classify_company(company: dict, jobs: list[dict]) -> dict:
    excerpts = get_excerpts(company["slug"], jobs)
    grounded = excerpts is not None

    if grounded:
        prompt = PROMPT_GROUNDED.format(name=company["name"], excerpts=excerpts)
    else:
        prompt = PROMPT_KNOWLEDGE.format(name=company["name"])

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    text = response["message"]["content"].strip()
    result = {
        "name": company["name"],
        "slug": company["slug"],
        "grounded": grounded,
    }

    for line in text.splitlines():
        if line.startswith("SUMMARY:"):
            result["summary"] = line.removeprefix("SUMMARY:").strip()
        elif line.startswith("INDUSTRY:"):
            result["industry"] = [t.strip() for t in line.removeprefix("INDUSTRY:").split(",")]
        elif line.startswith("STAGE:"):
            result["stage"] = line.removeprefix("STAGE:").strip()

    result["source_hash"] = source_hash(company)
    return result


def main():
    companies = json.loads(COMPANIES_FILE.read_text())
    jobs = json.loads(JOBS_FILE.read_text())

    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        existing = {c["slug"]: c for c in json.loads(OUTPUT_FILE.read_text())}

    to_classify = [
        c for c in companies
        if c["slug"] not in existing
        or existing[c["slug"]].get("source_hash") != source_hash(c)
    ]

    if not to_classify:
        print(f"All {len(companies)} companies already classified.")
        return

    print(f"Classifying {len(to_classify)} companies (skipping {len(existing)} cached)...")

    for i, company in enumerate(to_classify, 1):
        has_desc = bool(get_excerpts(company["slug"], jobs))
        mode = "grounded" if has_desc else "knowledge"
        print(f"  [{i}/{len(to_classify)}] {company['name']} ({mode})...", end=" ", flush=True)
        try:
            result = classify_company(company, jobs)
            existing[company["slug"]] = result
            print(result.get("summary", "done"))
        except Exception as e:
            print(f"ERROR: {e}")

    OUTPUT_FILE.write_text(json.dumps(list(existing.values()), indent=2))
    print(f"\nWritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
