#!/usr/bin/env python3
"""Render classified engineering jobs to one markdown file per job under jobs/."""

import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path


JOBS_FILE = Path(__file__).parent.parent / "data" / "jobs_raw.json"
CLASSIFIED_FILE = Path(__file__).parent.parent / "data" / "jobs_classified.json"
COMPANIES_FILE = Path(__file__).parent.parent / "data" / "companies_classified.json"

HASH_MARKER = "render_hash: "


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")


def render_hash(job: dict, classification: dict) -> str:
    skills_str = ",".join(classification.get("skills") or [])
    key = f"{job['id']}:{job['title']}:{job.get('raw_text', '')[:200]}:{classification.get('job_summary', '')}:{skills_str}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def format_date(iso: str | None) -> str:
    if not iso:
        return "Unknown"
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except ValueError:
        return iso


def render_job(job: dict, classification: dict, company_summary: str | None) -> str:
    location = job.get("location") or "Not specified"
    remote_str = {True: "Remote", False: "On-site"}.get(job.get("remote"), "Not specified")

    posted = format_date(job.get("posted_at"))
    first_seen = job.get("first_seen") or date.today().isoformat()
    raw_text = (job.get("raw_text") or "").strip()
    job_summary = classification.get("job_summary") or ""
    skills = classification.get("skills") or []
    rhash = render_hash(job, classification)

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
        f"{HASH_MARKER}{rhash}",
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
    JOBS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent / "jobs" / "jobs"

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

        if read_hash(path) == render_hash(job, cl):
            skipped += 1
            continue

        path.write_text(render_job(job, cl, company_summary))
        written += 1

    removed = 0
    for stale_path in JOBS_DIR.rglob("*.md"):
        if stale_path not in written_paths:
            stale_path.unlink()
            removed += 1
            if not any(stale_path.parent.iterdir()):
                stale_path.parent.rmdir()

    print(f"Written: {written}, Skipped (unchanged): {skipped}, Removed (stale): {removed}")


if __name__ == "__main__":
    main()
