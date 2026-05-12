#!/usr/bin/env python3
"""Fetch jobs from all companies in data/companies.json."""

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from scrapers import ats_greenhouse, ats_lever, ats_ashby
from scrapers._base import Job, ScraperError


DATA_DIR = Path("data")
COMPANIES_FILE = DATA_DIR / "companies.json"
OUTPUT_FILE = DATA_DIR / "jobs_raw.json"

SCRAPERS = {
    "greenhouse": ats_greenhouse.scrape,
    "lever": ats_lever.scrape,
    "ashby": ats_ashby.scrape,
}


def serialize_job(job: Job) -> dict:
    d = asdict(job)
    if d.get("posted_at"):
        d["posted_at"] = d["posted_at"].isoformat()
    return d


def main():
    companies = json.loads(COMPANIES_FILE.read_text())

    # Preserve first_seen dates and fetched descriptions across runs
    prev: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        for j in json.loads(OUTPUT_FILE.read_text()):
            prev[j["id"]] = j

    today = date.today().isoformat()
    all_jobs: list[dict] = []
    errors: list[str] = []
    new_count = closed_count = 0

    for company in companies:
        ats = company["ats"]
        name = company["name"]
        slug = company["slug"]

        scraper = SCRAPERS.get(ats)
        if not scraper:
            print(f"  [skip] {name}: unknown ATS '{ats}'")
            continue

        print(f"  Fetching {name} ({ats}/{slug})...", end=" ", flush=True)
        try:
            jobs = scraper(name, slug)
            for job in jobs:
                d = serialize_job(job)
                old = prev.get(d["id"])
                if old:
                    d["first_seen"] = old.get("first_seen", today)
                    if old.get("raw_text"):
                        d["raw_text"] = old["raw_text"]
                else:
                    d["first_seen"] = today
                    new_count += 1
                all_jobs.append(d)
            print(f"{len(jobs)} jobs")
        except ScraperError as e:
            print(f"ERROR")
            errors.append(str(e))

    closed_count = len(prev) - sum(1 for j in all_jobs if j["id"] in prev)

    print(f"\nTotal: {len(all_jobs)} jobs from {len(companies)} companies")
    print(f"New: {new_count}  |  Closed since last run: {closed_count}")

    OUTPUT_FILE.write_text(json.dumps(all_jobs, indent=2))
    print(f"Written to {OUTPUT_FILE}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
