#!/usr/bin/env python3
"""
Fetch full job descriptions for Greenhouse jobs.

The Greenhouse listing API returns metadata only. This script hits the
per-job detail endpoint to get the description HTML, strips it to plain
text, and writes results back into data/jobs_raw.json.

Already-fetched descriptions are skipped (cached by job ID). Only
Greenhouse jobs are processed — Lever and Ashby return descriptions
in their listing endpoints.

Usage:
    python fetch_descriptions.py
"""

import html
import json
import re
import time
from pathlib import Path

import httpx

JOBS_FILE = Path("data/jobs_raw.json")
DETAIL_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
REQUEST_DELAY = 0.15  # seconds between requests per company


def html_to_text(raw: str) -> str:
    text = html.unescape(raw)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>|</li>|</h[1-6]>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_description(slug: str, job_id: str, client: httpx.Client) -> str | None:
    url = DETAIL_URL.format(slug=slug, job_id=job_id)
    try:
        r = client.get(url, timeout=12)
        r.raise_for_status()
        content = r.json().get("content", "")
        return html_to_text(content) if content else None
    except Exception:
        return None


def extract_greenhouse_id(job_id: str) -> str:
    # job_id format: "greenhouse-{slug}-{numeric_id}"
    return job_id.rsplit("-", 1)[-1]


def main():
    jobs = json.loads(JOBS_FILE.read_text())

    gh_jobs = [
        j for j in jobs
        if j["source"] == "greenhouse" and not j.get("raw_text", "").strip()
    ]
    already_have = sum(
        1 for j in jobs
        if j["source"] == "greenhouse" and j.get("raw_text", "").strip()
    )

    print(f"Greenhouse jobs: {len(gh_jobs)} need descriptions, {already_have} already fetched\n")

    if not gh_jobs:
        print("Nothing to do.")
        return

    # Group by slug to be polite with per-company rate limiting
    by_slug: dict[str, list] = {}
    for job in gh_jobs:
        by_slug.setdefault(job["company_slug"], []).append(job)

    job_index = {j["id"]: j for j in jobs}
    fetched = failed = 0

    with httpx.Client(follow_redirects=True) as client:
        for slug, slug_jobs in by_slug.items():
            company = slug_jobs[0]["company"]
            print(f"  {company} ({len(slug_jobs)} jobs)...", end=" ", flush=True)
            slug_fetched = 0

            for job in slug_jobs:
                gh_id = extract_greenhouse_id(job["id"])
                text = fetch_description(slug, gh_id, client)
                if text:
                    job_index[job["id"]]["raw_text"] = text
                    slug_fetched += 1
                    fetched += 1
                else:
                    failed += 1
                time.sleep(REQUEST_DELAY)

            print(f"{slug_fetched}/{len(slug_jobs)}")

    JOBS_FILE.write_text(json.dumps(list(job_index.values()), indent=2))
    print(f"\nFetched: {fetched}, Failed: {failed}")
    print(f"Written to {JOBS_FILE}")


if __name__ == "__main__":
    main()
