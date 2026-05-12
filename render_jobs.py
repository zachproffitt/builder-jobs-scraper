#!/usr/bin/env python3
"""
Render classified engineering jobs to one markdown file per job under jobs/.

Reads:
  data/jobs_raw.json            — job metadata + description text
  data/jobs_classified.json     — is_engineering flag + job_summary per job_id
  data/companies_classified.json — company summary per slug

Only renders jobs where is_engineering=True. Skips jobs whose source_hash
matches the existing rendered file (delta logic). Deletes rendered files for
jobs that are no longer present or no longer classified as engineering.

Usage:
    python render.py
"""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path


import sys

JOBS_FILE = Path("data/jobs_raw.json")
CLASSIFIED_FILE = Path("data/jobs_classified.json")
COMPANIES_FILE = Path("data/companies_classified.json")
# Default: sibling builder-jobs repo's jobs/ subdirectory
JOBS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "jobs" / "jobs"

HASH_MARKER = "source_hash: "


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")


def source_hash(job: dict, classification: dict) -> str:
    skills_str = ",".join(classification.get("skills") or [])
    key = f"{job['id']}:{job['title']}:{job.get('raw_text', '')[:200]}:{classification.get('job_summary', '')}:{skills_str}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def format_date(iso: str | None) -> str:
    if not iso:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return iso


def render_job(job: dict, classification: dict, company_summary: str | None) -> str:
    location = job.get("location") or "Not specified"
    remote = job.get("remote")
    if remote is True:
        remote_str = "Remote"
    elif remote is False:
        remote_str = "On-site"
    else:
        remote_str = "Not specified"

    posted = format_date(job.get("posted_at"))
    first_seen = job.get("first_seen") or date.today().isoformat()
    raw_text = (job.get("raw_text") or "").strip()
    job_summary = classification.get("job_summary") or ""
    skills = classification.get("skills") or []
    shash = source_hash(job, classification)

    lines = [
        "---",
        f"id: {job['id']}",
        f"company: {job['company']}",
        f"title: {job['title']}",
        f"source: {job['source']}",
        f"location: {location}",
        f"remote: {remote_str}",
        f"posted_at: {posted}",
        f"first_seen: {first_seen}",
        f"url: {job['url']}",
        f"summary: {job_summary}",
        f"skills: {', '.join(skills)}",
        f"{HASH_MARKER}{shash}",
        "---",
        "",
        f"# {job['title']}",
        "",
    ]

    if company_summary:
        lines += [f"**{job['company']}** — {company_summary}", ""]

    if job_summary:
        lines += [f"> {job_summary}", ""]

    lines += [
        "| Field | Value |",
        "|---|---|",
        f"| Company | {job['company']} |",
        f"| Location | {location} |",
        f"| Remote | {remote_str} |",
        f"| Posted | {posted} |",
        f"| First seen | {first_seen} |",
        f"| Source | {job['source']} |",
        "",
        f"[Apply]({job['url']})",
        "",
    ]

    if raw_text:
        lines += ["---", "", raw_text, ""]

    return "\n".join(lines)


def read_hash(path: Path) -> str | None:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(HASH_MARKER):
                return line.removeprefix(HASH_MARKER).strip()
    except FileNotFoundError:
        pass
    return None


def main():
    jobs = json.loads(JOBS_FILE.read_text())

    classified: dict[str, dict] = {}
    if CLASSIFIED_FILE.exists():
        classified = json.loads(CLASSIFIED_FILE.read_text())

    company_summaries: dict[str, str] = {}
    if COMPANIES_FILE.exists():
        for c in json.loads(COMPANIES_FILE.read_text()):
            company_summaries[c["slug"]] = c.get("summary", "")

    JOBS_DIR.mkdir(exist_ok=True)

    eng_jobs = [
        j for j in jobs
        if classified.get(j["id"], {}).get("is_engineering") is True
    ]

    print(f"Engineering jobs to render: {len(eng_jobs)} / {len(jobs)} total")

    # Track which paths we write so we can prune stale files
    written_paths: set[Path] = set()
    written = skipped = 0

    for job in eng_jobs:
        cl = classified[job["id"]]
        company_slug = job.get("company_slug", "")
        company_summary = company_summaries.get(company_slug)

        company_dir = JOBS_DIR / slugify(job["company"])
        company_dir.mkdir(exist_ok=True)

        path = company_dir / f"{job['id']}.md"
        written_paths.add(path)

        shash = source_hash(job, cl)
        if read_hash(path) == shash:
            skipped += 1
            continue

        path.write_text(render_job(job, cl, company_summary))
        written += 1

    # Remove rendered files for jobs no longer classified as engineering
    removed = 0
    for existing in JOBS_DIR.rglob("*.md"):
        if existing not in written_paths:
            existing.unlink()
            removed += 1
            # Remove empty company dirs
            if not any(existing.parent.iterdir()):
                existing.parent.rmdir()

    print(f"Written: {written}, Skipped (unchanged): {skipped}, Removed (stale): {removed}")


if __name__ == "__main__":
    main()
