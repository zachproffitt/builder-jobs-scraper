#!/usr/bin/env python3
"""
Fetch descriptions for Greenhouse jobs that don't have one yet.

The Greenhouse listing API returns metadata only. This script hits the
per-job detail endpoint, strips HTML to plain text, and writes results
back into data/jobs_raw.json.

By default only processes jobs first_seen today so each daily run is fast.
Use --all to backfill all Greenhouse jobs without descriptions.

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
DETAIL_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
WORKERS = 10


def fetch_description(job: dict) -> str | None:
    slug = job.get("company_slug", "")
    greenhouse_id = job["id"].rsplit("-", 1)[-1]
    url = DETAIL_URL.format(slug=slug, job_id=greenhouse_id)
    try:
        r = httpx.get(url, timeout=15)
        r.raise_for_status()
        content = r.json().get("content", "")
        return html_to_text(content) if content else None
    except Exception:
        return None


def main():
    fetch_all = "--all" in sys.argv
    today = datetime.now(timezone.utc).date().isoformat()

    jobs = json.loads(JOBS_FILE.read_text())

    to_fetch = [
        j for j in jobs
        if j.get("source") == "greenhouse"
        and not j.get("raw_text", "").strip()
        and (fetch_all or j.get("first_seen") == today)
    ]

    if not to_fetch:
        scope = "all" if fetch_all else "today's"
        print(f"No {scope} Greenhouse jobs need descriptions")
        return

    scope = "all" if fetch_all else "today's new"
    print(f"Fetching descriptions for {len(to_fetch)} {scope} Greenhouse jobs...")

    job_index = {j["id"]: j for j in jobs}
    lock = threading.Lock()
    fetched = failed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_description, job): job for job in to_fetch}
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
