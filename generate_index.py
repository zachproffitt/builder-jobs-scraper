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
        by_date[fm.get("first_seen", "unknown")].append({
            "title": fm.get("title", ""),
            "company": fm.get("company", ""),
            "summary": fm.get("summary", ""),
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
        f"**{total} open roles** · updated daily",
        "",
        "---",
        "",
    ]

    for date in sorted(by_date.keys(), reverse=True):
        jobs = by_date[date]
        jobs.sort(key=lambda j: j["posted_at"], reverse=True)
        try:
            label = datetime.strptime(date, "%Y-%m-%d").strftime("%B %-d, %Y")
        except ValueError:
            label = date
        lines.append(f"## {label}")
        lines.append("")
        for j in jobs:
            lines.append(f"### [{j['title']}]({j['path']})")
            if j["summary"]:
                lines.append(f"**{j['company']}** — {j['summary']}")
            else:
                lines.append(f"**{j['company']}**")
            lines.append("")

    README.write_text("\n".join(lines))
    print(f"Written {README}")


if __name__ == "__main__":
    main()
