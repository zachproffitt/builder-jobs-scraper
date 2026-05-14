#!/usr/bin/env python3
"""
Fetch descriptions for jobs that don't have one yet.

Greenhouse:  per-job API endpoint
BambooHR:    per-job detail endpoint
Breezy:      job page HTML
Workable:    job page HTML

By default only processes jobs first_seen today.
Use --all to backfill all jobs without descriptions.

Usage:
    python fetch_job_descriptions.py          # today's new jobs only
    python fetch_job_descriptions.py --all    # all without descriptions
"""

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scrapers._base import html_to_text

JOBS_FILE = Path(__file__).parent.parent / "data" / "jobs_raw.json"
WORKERS = 10

GREENHOUSE_DETAIL_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
BAMBOO_DETAIL_URL = "https://{slug}.bamboohr.com/careers/{job_id}/detail"


def fetch_greenhouse(job: dict, client: httpx.Client) -> str | None:
    slug = job.get("company_slug", "")
    job_id = job["id"].rsplit("-", 1)[-1]
    url = GREENHOUSE_DETAIL_URL.format(slug=slug, job_id=job_id)
    try:
        r = client.get(url, timeout=15)
        r.raise_for_status()
        content = r.json().get("content", "")
        return html_to_text(content) if content else None
    except Exception:
        return None


def fetch_bamboo(job: dict, client: httpx.Client) -> str | None:
    slug = job.get("company_slug", "")
    job_id = job["id"].rsplit("-", 1)[-1]
    url = BAMBOO_DETAIL_URL.format(slug=slug, job_id=job_id)
    try:
        r = client.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        description = r.json()["result"]["jobOpening"].get("description", "")
        return html_to_text(description) if description else None
    except Exception:
        return None


def fetch_html(job: dict, client: httpx.Client) -> str | None:
    url = job.get("url", "")
    if not url:
        return None
    try:
        r = client.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        r.raise_for_status()
        return html_to_text(r.text) or None
    except Exception:
        return None


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "bamboo": fetch_bamboo,
    "breezy": fetch_html,
    "workable": fetch_html,
}


def main():
    fetch_all = "--all" in sys.argv
    today = datetime.now(timezone.utc).date().isoformat()

    jobs = json.loads(JOBS_FILE.read_text())

    to_fetch = [
        j for j in jobs
        if j.get("source") in FETCHERS
        and not j.get("raw_text", "").strip()
        and (fetch_all or j.get("first_seen") == today)
    ]

    if not to_fetch:
        scope = "all" if fetch_all else "today's"
        print(f"No {scope} jobs need descriptions")
        return

    scope = "all" if fetch_all else "today's new"
    print(f"Fetching descriptions for {len(to_fetch)} {scope} jobs...")

    job_index = {j["id"]: j for j in jobs}
    lock = threading.Lock()
    fetched = failed = 0

    with httpx.Client() as client:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {
                executor.submit(FETCHERS[job["source"]], job, client): job
                for job in to_fetch
            }
            for future in as_completed(futures):
                job = futures[future]
                desc = future.result()
                with lock:
                    if desc:
                        job_index[job["id"]]["raw_text"] = desc
                        fetched += 1
                    else:
                        failed += 1

    JOBS_FILE.write_text(json.dumps(list(job_index.values()), indent=2))
    print(f"Fetched: {fetched}, Failed: {failed}")


if __name__ == "__main__":
    main()
