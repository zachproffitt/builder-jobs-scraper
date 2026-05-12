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
FORMAT_VERSION = "6"  # bump to force re-render of all files
SKILL_COLOR = "3B82F6"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")


def skill_badge(skill: str) -> str:
    label = skill.strip().replace("-", "--").replace("_", "__").replace(" ", "_")
    label = (label
        .replace("(", "%28").replace(")", "%29")
        .replace(",", "%2C").replace("/", "%2F")
        .replace("+", "%2B").replace("#", "%23"))
    return f"![{skill}](https://img.shields.io/badge/{label}-{SKILL_COLOR}?style=flat-square)"


def render_hash(job: dict, classification: dict) -> str:
    skills_str = ",".join(classification.get("skills") or [])
    level = classification.get("level") or ""
    key = f"v{FORMAT_VERSION}:{job['id']}:{job['title']}:{job.get('raw_text', '')[:200]}:{classification.get('job_summary', '')}:{skills_str}:{level}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def clean_location(location: str, is_remote: bool) -> str:
    """Strip 'remote' from location string when the Remote tag is already shown."""
    if not is_remote or not location:
        return location
    cleaned = re.sub(r"\s*[-–,]\s*remote\b", "", location, flags=re.I)
    cleaned = re.sub(r"\bremote\s*[-–,]\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*remote\s*$", "", cleaned, flags=re.I)
    return cleaned.strip().strip("-").strip(",").strip()


def format_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except ValueError:
        return iso


def pretty_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %-d, %Y")
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
    level = classification.get("level")
    rhash = render_hash(job, classification)

    is_remote = job.get("remote") is True
    display_location = clean_location(location, is_remote)

    # HTML comment holds machine-readable metadata — not rendered by GitHub
    meta_lines = [
        "<!--",
        f"id: {job['id']}",
        f"company: {job['company']}",
        f"title: {job['title']}",
        f"source: {job['source']}",
        f"location: {location}",
        f"remote: {remote_str}",
        f"posted_at: {posted or 'Unknown'}",
        f"first_seen: {first_seen}",
        f"url: {job['url']}",
        f"summary: {job_summary}",
        f"skills: {', '.join(skills)}",
        f"level: {level or ''}",
        f"render_hash: {rhash}",
        "-->",
    ]

    # Two-line meta: company name prominent, details below
    detail_parts = []
    if display_location and display_location != "Not specified":
        detail_parts.append(display_location)
    if remote_str == "Remote":
        detail_parts.append("`Remote`")
    elif remote_str == "On-site":
        detail_parts.append("On-site")
    if level:
        detail_parts.append(f"`{level.capitalize()}`")

    company_line = f"**{job['company']}**"
    meta_line = (company_line + "  \n" + " · ".join(detail_parts)) if detail_parts else company_line

    lines = meta_lines + [
        "",
        f"# {job['title']}",
        "",
        meta_line,
        "",
    ]

    if company_summary:
        lines += [f"> {company_summary}", ""]

    if job_summary:
        lines += [f"_{job_summary}_", ""]

    if skills:
        lines += [" ".join(skill_badge(s) for s in skills), ""]

    date_label = f"Posted {pretty_date(posted)}" if posted else f"First seen {pretty_date(first_seen)}"
    lines += [f"<sub>{date_label}</sub>", ""]

    lines += [f"**[→ Apply]({job['url']})**", ""]

    if raw_text:
        lines += ["---", "", raw_text, "", "---", "", f"**[→ Apply]({job['url']})**", ""]

    return "\n".join(lines)


def read_hash(path: Path) -> str | None:
    try:
        for line in path.read_text().splitlines():
            if line.startswith("render_hash:"):
                return line.removeprefix("render_hash:").strip()
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
