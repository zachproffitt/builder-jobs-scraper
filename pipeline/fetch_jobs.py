#!/usr/bin/env python3
"""Fetch jobs from all companies in data/companies.json."""

import json
import sys
from dataclasses import asdict
from datetime import date, timedelta, timezone, datetime
from pathlib import Path

from scrapers import ats_greenhouse, ats_lever, ats_ashby, ats_smartrecruiters, ats_bamboo, ats_breezy, ats_workable, ats_workday, ats_eightfold
from scrapers._base import Job, ScraperError


DATA_DIR = Path(__file__).parent.parent / "data"
COMPANIES_FILE = DATA_DIR / "companies.json"
OUTPUT_FILE = DATA_DIR / "jobs_raw.json"
SEEN_FILE = DATA_DIR / "seen_jobs.json"
SEEN_COMPANIES_FILE = DATA_DIR / "seen_companies.json"
LOG_FILE = DATA_DIR / "pipeline.log"
ARCHIVE_DATE = "2020-01-01"  # first-fetch jobs for new companies get this date
WINDOW_DAYS = 14


def log_error(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] fetch_jobs: {message}\n")

SCRAPERS = {
    "greenhouse": ats_greenhouse.scrape,
    "lever": ats_lever.scrape,
    "ashby": ats_ashby.scrape,
    "smartrecruiters": ats_smartrecruiters.scrape,
    "bamboo": ats_bamboo.scrape,
    "breezy": ats_breezy.scrape,
    "workable": ats_workable.scrape,
    "workday": ats_workday.scrape,
    "eightfold": ats_eightfold.scrape,
}


def serialize_job(job: Job) -> dict:
    d = asdict(job)
    if d.get("posted_at"):
        d["posted_at"] = d["posted_at"].isoformat()
    return d


def main():
    companies = json.loads(COMPANIES_FILE.read_text())

    # Permanent ID registry — never pruned, survives the rolling window
    seen: dict[str, str] = {}
    if SEEN_FILE.exists():
        seen = json.loads(SEEN_FILE.read_text())

    # Preserve descriptions from the rolling window
    prev: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        for j in json.loads(OUTPUT_FILE.read_text()):
            prev[j["id"]] = j

    # Companies seen before — new companies have all jobs archived on first fetch
    seen_companies: dict[str, str] = {}
    if SEEN_COMPANIES_FILE.exists():
        seen_companies = json.loads(SEEN_COMPANIES_FILE.read_text())

    today = datetime.now(timezone.utc).date().isoformat()
    now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    all_jobs: list[dict] = []
    error_count = 0
    new_count = closed_count = archived_count = 0

    for company in companies:
        ats = company["ats"]
        name = company["name"]
        slug = company["slug"]

        scraper = SCRAPERS.get(ats)
        if not scraper:
            print(f"  [skip] {name}: unknown ATS '{ats}'")
            continue

        company_key = f"{ats}:{slug}"
        is_new_company = company_key not in seen_companies

        print(f"  Fetching {name} ({ats}/{slug})...", end=" ", flush=True)
        try:
            jobs = scraper(name, slug)
            for job in jobs:
                d = serialize_job(job)
                job_id = d["id"]
                if job_id in seen:
                    d["first_seen"] = seen[job_id]
                    if prev.get(job_id, {}).get("first_seen_at"):
                        d["first_seen_at"] = prev[job_id]["first_seen_at"]
                elif is_new_company:
                    # Archive all first-fetch jobs for new companies
                    d["first_seen"] = ARCHIVE_DATE
                    seen[job_id] = ARCHIVE_DATE
                    archived_count += 1
                else:
                    d["first_seen"] = today
                    d["first_seen_at"] = now_ts
                    seen[job_id] = today
                    new_count += 1
                if prev.get(job_id, {}).get("raw_text"):
                    d["raw_text"] = prev[job_id]["raw_text"]
                all_jobs.append(d)
            seen_companies[company_key] = today
            label = " [new company — archived]" if is_new_company else ""
            print(f"{len(jobs)} jobs{label}")
        except ScraperError as e:
            error_count += 1
            print("ERROR")
            log_error(f"scraper error for {name} ({ats}/{slug}): {e}")

    closed_count = len(prev) - sum(1 for j in all_jobs if j["id"] in prev)

    # Drop jobs outside the rolling window
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS)).isoformat()
    before = len(all_jobs)
    all_jobs = [j for j in all_jobs if j.get("first_seen", today) >= cutoff]
    aged_out = before - len(all_jobs)

    print(f"\nTotal: {len(all_jobs)} jobs from {len(companies)} companies")
    print(f"New: {new_count}  |  Closed: {closed_count}  |  Aged out (>{WINDOW_DAYS}d): {aged_out}  |  Archived (new companies): {archived_count}  |  Errors: {error_count}")

    OUTPUT_FILE.write_text(json.dumps(all_jobs, indent=2))
    SEEN_FILE.write_text(json.dumps(seen, indent=2))
    SEEN_COMPANIES_FILE.write_text(json.dumps(seen_companies, indent=2))
    print(f"Written to {OUTPUT_FILE}")
    if error_count:
        print(f"  {error_count} scraper errors logged to {LOG_FILE.name}")


if __name__ == "__main__":
    main()
