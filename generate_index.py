#!/usr/bin/env python3
"""
Generate README.md for the jobs repo by scanning all rendered job files.

Reads every *.md file under JOBS_REPO (excluding README.md itself), parses
frontmatter, groups by first_seen date, and writes README.md with newest
dates at the top.

Usage:
    python generate_index.py [jobs_repo_path]

JOBS_REPO defaults to ../jobs relative to this script.
"""

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


JOBS_REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "jobs"
README = JOBS_REPO / "README.md"
SKILL_COLOR = "3B82F6"


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    fm_text = text[3:end]
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def skill_badge(skill: str) -> str:
    label = skill.strip().replace("-", "--").replace("_", "__").replace(" ", "_")
    label = label.replace("+", "%2B").replace("#", "%23")
    return f"![{skill}](https://img.shields.io/badge/{label}-{SKILL_COLOR}?style=flat-square)"


def format_meta(fm: dict) -> str:
    company = fm.get("company", "")
    location = fm.get("location", "").strip()
    remote = fm.get("remote", "").strip()

    if " | " in location:
        location = location.split(" | ")[0].strip()
    if location in ("Not specified", ""):
        location = ""

    parts = [f"**{company}**"]
    if location:
        parts.append(location)
    if remote == "Remote":
        parts.append("`Remote`")

    return " · ".join(parts)


def main():
    if not JOBS_REPO.exists():
        print(f"Jobs repo not found: {JOBS_REPO}")
        sys.exit(1)

    by_date: dict[str, list[dict]] = defaultdict(list)

    for md in sorted(JOBS_REPO.rglob("*.md")):
        if md.name == "README.md":
            continue
        fm = parse_frontmatter(md)
        if not fm.get("id"):
            continue
        skills_raw = fm.get("skills", "")
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if skills_raw else []
        by_date[fm.get("first_seen", "unknown")].append({
            "title": fm.get("title", ""),
            "company": fm.get("company", ""),
            "meta": format_meta(fm),
            "summary": fm.get("summary", ""),
            "skills": skills,
            "posted_at": fm.get("posted_at", ""),
            "path": str(md.relative_to(JOBS_REPO)),
        })

    total = sum(len(v) for v in by_date.values())
    print(f"Found {total} jobs across {len(by_date)} dates")

    lines = [
        "# Builder Jobs",
        "",
        "A job board for engineers who build things — software, hardware, firmware, ML systems.",
        "Roles are scraped daily from company career pages and filtered by an LLM to keep only",
        "positions where the person will primarily write code or build systems.",
        "",
        f"### {total} open roles &nbsp;·&nbsp; updated daily",
        "",
    ]

    for date in sorted(by_date.keys(), reverse=True):
        jobs = by_date[date]
        jobs.sort(key=lambda j: j["company"].lower())
        try:
            label = datetime.strptime(date, "%Y-%m-%d").strftime("%B %-d, %Y")
        except ValueError:
            label = date
        lines.append("<br>")
        lines.append("")
        lines.append(f"## {label}")
        lines.append("")
        for j in jobs:
            lines.append(f"### [{j['title']}]({j['path']})")
            lines.append(j["meta"])
            if j["summary"]:
                lines.append("")
                lines.append(f"_{j['summary']}_")
            if j["skills"]:
                lines.append("")
                lines.append(" ".join(skill_badge(s) for s in j["skills"]))
            lines.append("")
            lines.append("---")
            lines.append("")

    README.write_text("\n".join(lines))
    print(f"Written {README}")


if __name__ == "__main__":
    main()
