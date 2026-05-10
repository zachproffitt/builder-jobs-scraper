#!/usr/bin/env python3
"""Render jobs_raw.json into one markdown file per job under jobs/."""

import json
import re
from datetime import date
from pathlib import Path


DATA_FILE = Path("data/jobs_raw.json")
JOBS_DIR = Path("jobs")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")


def render_job(job: dict) -> str:
    location = job.get("location") or "Not specified"
    remote = job.get("remote")
    if remote is True:
        remote_str = "Remote"
    elif remote is False:
        remote_str = "On-site"
    else:
        remote_str = "Not specified"

    departments = ", ".join(job.get("departments") or []) or "Not specified"
    fetched = date.today().isoformat()
    raw_text = (job.get("raw_text") or "").strip()

    lines = [
        f"---",
        f"id: {job['id']}",
        f"company: {job['company']}",
        f"title: {job['title']}",
        f"source: {job['source']}",
        f"location: {location}",
        f"remote: {remote_str}",
        f"departments: {departments}",
        f"url: {job['url']}",
        f"fetched_at: {fetched}",
        f"---",
        f"",
        f"# {job['title']}",
        f"",
        f"| Field | Value |",
        f"|---|---|",
        f"| Company | {job['company']} |",
        f"| Location | {location} |",
        f"| Remote | {remote_str} |",
        f"| Department | {departments} |",
        f"| Source | {job['source']} |",
        f"",
        f"[Apply]({job['url']})",
        f"",
    ]

    if raw_text:
        lines += ["---", "", raw_text, ""]

    return "\n".join(lines)


def main():
    jobs = json.loads(DATA_FILE.read_text())
    JOBS_DIR.mkdir(exist_ok=True)

    written = 0
    for job in jobs:
        company_dir = JOBS_DIR / slugify(job["company"])
        company_dir.mkdir(exist_ok=True)

        filename = f"{job['id']}.md"
        path = company_dir / filename
        path.write_text(render_job(job))
        written += 1

    print(f"Rendered {written} jobs to {JOBS_DIR}/")


if __name__ == "__main__":
    main()
