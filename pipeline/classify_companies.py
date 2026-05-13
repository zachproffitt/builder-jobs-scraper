#!/usr/bin/env python3
"""Generate company summaries using Claude Haiku."""

import json
import os
import sys
import time
from pathlib import Path

COMPANIES_FILE = Path(__file__).parent.parent / "data" / "companies.json"
JOBS_FILE = Path(__file__).parent.parent / "data" / "jobs_raw.json"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "companies_classified.json"

BACKEND = os.environ.get("LLM_BACKEND", "claude")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
OLLAMA_MODEL = "qwen3:8b"

PROMPT = """\
Write 1-2 sentences describing what {name} builds and what domain they operate in. Use your training knowledge about this company.
Be specific and factual. Plain prose only — no markdown, no bullet points, no headers.
Do not use "leading", "innovative", "cutting-edge", "pioneering". Do not say you lack web access.
Start directly with the company name or what they build.{job_context}

Company: {name}
Website: {website}
"""


def call_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except anthropic.RateLimitError:
            time.sleep(2 ** attempt)
    raise RuntimeError("Rate limit exceeded after retries")


def call_ollama(prompt: str) -> str:
    import ollama
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1, "num_ctx": 2048},
        keep_alive="10m",
    )
    return response["message"]["content"].strip()


def call_llm(prompt: str) -> str:
    return call_claude(prompt) if BACKEND == "claude" else call_ollama(prompt)


def main():
    classify_all = "--all" in sys.argv

    companies = json.loads(COMPANIES_FILE.read_text())

    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        for c in json.loads(OUTPUT_FILE.read_text()):
            existing[c["slug"]] = c

    # Build job lookup by company slug for context
    job_lookup: dict[str, list[dict]] = {}
    if JOBS_FILE.exists():
        for job in json.loads(JOBS_FILE.read_text()):
            slug = job.get("company_slug", "")
            if slug:
                job_lookup.setdefault(slug, []).append(job)

    supported_ats = {"greenhouse", "lever", "ashby", "smartrecruiters"}
    def needs_classify(c: dict) -> bool:
        if classify_all:
            return True
        if c["slug"] not in existing:
            return True
        summary = existing[c["slug"]].get("summary", "")
        bad = any(phrase in summary.lower() for phrase in [
            "don't have access", "cannot browse", "can't browse",
            "can't verify", "cannot verify", "i don't have",
            "could you provide", "please provide",
        ])
        return bad or not summary

    to_process = [c for c in companies if c.get("ats") in supported_ats and needs_classify(c)]

    print(f"Backend: {BACKEND}")
    print(f"{len(to_process)} companies to classify ({len(existing)} already done)\n")

    if not to_process:
        print("All companies already classified. Use --all to reclassify.")
        return

    errors = 0
    for i, company in enumerate(to_process, 1):
        slug = company["slug"]
        name = company["name"]
        website = company.get("website", "")

        # Use a sample job title for extra context if available
        jobs = job_lookup.get(slug, [])
        sample = next((j for j in jobs if j.get("raw_text")), None)
        if sample:
            job_context = f"\nSample job title: {sample['title']}"
        else:
            job_context = ""

        prompt = PROMPT.format(name=name, website=website, job_context=job_context)

        try:
            raw = call_llm(prompt)
            # Strip markdown headers and leading whitespace
            lines = [l for l in raw.splitlines() if not l.startswith("#")]
            summary = " ".join(l.strip() for l in lines if l.strip())
            # Discard responses where the model said it couldn't answer
            bad = any(phrase in summary.lower() for phrase in [
                "don't have access", "cannot browse", "can't browse",
                "can't verify", "cannot verify", "i don't have",
                "could you provide", "please provide",
            ])
            if bad:
                print(f"  [{i:>3}/{len(to_process)}] SKIP {name}: model refused (will retry with --all)")
                continue
            existing[slug] = {"slug": slug, "name": name, "summary": summary}
            print(f"  [{i:>3}/{len(to_process)}] {name}: {summary[:80]}")
        except Exception as e:
            errors += 1
            print(f"  [{i:>3}/{len(to_process)}] ERROR {name}: {e}")

    OUTPUT_FILE.write_text(json.dumps(list(existing.values()), indent=2))
    print(f"\nDone. Written to {OUTPUT_FILE}")
    if errors:
        print(f"{errors} errors — re-run to retry")


if __name__ == "__main__":
    main()
