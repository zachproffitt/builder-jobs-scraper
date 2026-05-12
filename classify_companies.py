#!/usr/bin/env python3
"""
Generate a one-sentence company summary for each company in data/companies.json.

Uses meta_description (scraped from homepage) and/or job description excerpts
as grounding. Companies with no grounding are skipped — we only output summaries
we can be confident in.

Results are cached in data/companies_classified.json and only regenerated when
the company's source data changes (tracked via source_hash).

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

PROMPT = """/no_think
You are writing a one-sentence company summary for a software engineering job board.

Rules:
- One sentence, maximum 20 words.
- State what the company builds or does. Be specific.
- No marketing language, no adjectives like "leading" or "powerful".
- Write as a plain fact.

Bad: "X is a fast-growing company that empowers developers with cutting-edge tools."
Good: "X builds open-source Postgres tooling used by backend developers."

Company: {name}
{sources}

Respond with only the summary sentence. No labels, no extra text.
"""


def source_hash(company: dict) -> str:
    return hashlib.md5(json.dumps(company, sort_keys=True).encode()).hexdigest()[:8]


def get_excerpts(slug: str, jobs: list[dict], n: int = 3, chars: int = 600) -> "str | None":
    matches = [j for j in jobs if j.get("company_slug") == slug and j.get("raw_text", "").strip()]
    if not matches:
        return None
    parts = [job["raw_text"].strip()[:chars] for job in matches[:n]]
    return "\n\n---\n\n".join(parts)


def classify_company(company: dict, jobs: list[dict]) -> "dict | None":
    meta = company.get("meta_description", "").strip()
    excerpts = get_excerpts(company["slug"], jobs)

    if not meta and not excerpts:
        return None  # No grounding — skip rather than hallucinate

    sources = []
    if meta:
        sources.append(f"Website: {meta}")
    if excerpts:
        sources.append(f"Job description excerpts:\n{excerpts}")

    prompt = PROMPT.format(name=company["name"], sources="\n\n".join(sources))

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    summary = response["message"]["content"].strip().strip('"')

    return {
        "name": company["name"],
        "slug": company["slug"],
        "summary": summary,
        "source_hash": source_hash(company),
    }


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

    skippable = [c for c in to_classify if not c.get("meta_description") and not get_excerpts(c["slug"], jobs)]
    to_run = [c for c in to_classify if c not in skippable]

    print(f"{len(to_run)} to classify, {len(existing)} cached, {len(skippable)} skipped (no grounding)\n")

    if not to_run:
        print("Nothing to do.")
        return

    for i, company in enumerate(to_run, 1):
        print(f"  [{i:>3}/{len(to_run)}] {company['name']}...", end=" ", flush=True)
        try:
            result = classify_company(company, jobs)
            if result:
                existing[company["slug"]] = result
                print(result["summary"])
            else:
                print("skipped")
        except Exception as e:
            print(f"ERROR: {e}")

    OUTPUT_FILE.write_text(json.dumps(list(existing.values()), indent=2))
    print(f"\nWritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
