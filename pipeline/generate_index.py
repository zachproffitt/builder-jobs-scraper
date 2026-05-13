#!/usr/bin/env python3
"""Generate README.md for the jobs repo by scanning all rendered job files."""

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


JOBS_REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent / "jobs"
README = JOBS_REPO / "README.md"
COMPANIES_FILE = Path(__file__).parent.parent / "data" / "companies.json"
SKILL_COLOR = "3B82F6"


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("<!--"):
        return {}
    end = text.find("-->")
    if end == -1:
        return {}
    meta_text = text[4:end]
    fm = {}
    for line in meta_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def skill_badge(skill: str) -> str:
    label = skill.strip().replace("-", "--").replace("_", "__").replace(" ", "_")
    label = (label
        .replace("(", "%28").replace(")", "%29")
        .replace(",", "%2C").replace("/", "%2F")
        .replace("+", "%2B").replace("#", "%23"))
    return f"![{skill}](https://img.shields.io/badge/{label}-{SKILL_COLOR}?style=flat-square)"


def format_meta(fm: dict) -> str:
    company = fm.get("company", "")
    location = fm.get("location", "").strip()
    remote = fm.get("remote", "").strip()
    hybrid = fm.get("hybrid", "").strip()
    level = fm.get("level", "").strip()
    comp = fm.get("comp", "").strip()
    comp_extras_raw = fm.get("comp_extras", "").strip()
    comp_extras = [s.strip() for s in comp_extras_raw.split(",") if s.strip()] if comp_extras_raw else []

    if " | " in location:
        location = location.split(" | ")[0].strip()
    if location in ("Not specified", ""):
        location = ""

    if remote == "Remote" and location:
        location = re.sub(r"\s*\(\s*(?:remote|hybrid)\s*\)", "", location, flags=re.I)
        location = re.sub(r"\s*[-–,|]\s*(?:remote|hybrid)\b", "", location, flags=re.I)
        location = re.sub(r"\b(?:remote|hybrid)\s*[-–,|]\s*", "", location, flags=re.I)
        location = re.sub(r"^\s*(?:remote|hybrid)\s*$", "", location, flags=re.I)
        location = location.strip().strip("-").strip(",").strip("|").strip()

    parts = [f"**{company}**"]
    if location:
        parts.append(location)
    if level and level not in ("unclear", ""):
        parts.append(f"`{level.capitalize()}`")
    if remote == "Remote":
        parts.append("`Remote`")
    elif hybrid == "yes":
        parts.append("`Hybrid`")
    if comp:
        parts.append(f"`{comp}`")
    for extra in comp_extras:
        parts.append(f"`{extra.capitalize()}`")

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
            "first_seen_at": fm.get("first_seen_at", ""),
            "path": str(md.relative_to(JOBS_REPO)),
        })

    total = sum(len(v) for v in by_date.values())
    today = datetime.now().strftime("%Y-%m-%d")
    new_today = len(by_date.get(today, []))
    print(f"Found {total} jobs across {len(by_date)} dates ({new_today} new today)")

    all_timestamps = [j["first_seen_at"] for v in by_date.values() for j in v if j.get("first_seen_at")]
    last_run_str = ""
    if all_timestamps:
        last_run_dt = datetime.fromisoformat(max(all_timestamps))
        last_run_str = last_run_dt.strftime("%B %-d, %Y at %H:%M UTC")

    company_count = 0
    company_logos: dict[str, str] = {}
    if COMPANIES_FILE.exists():
        import json
        companies = json.loads(COMPANIES_FILE.read_text())
        company_count = len([c for c in companies if c.get("ats") in {"greenhouse", "lever", "ashby", "smartrecruiters"}])
        for c in companies:
            if c.get("website") and c.get("name"):
                domain = c["website"].removeprefix("https://").removeprefix("http://").split("/")[0]
                company_logos[c["name"]] = domain

    lines = [
        "# Builder Jobs",
        "",
        "For engineers who build.",
        "Roles are [scraped](https://github.com/zachproffitt/builder-jobs-scraper) hourly from company career pages and classified by Claude Haiku 4.5 — curation keeps the signal",
        "high enough that browsing everything new takes a few minutes and gives you a broader picture of the market.",
        "Listings older than 14 days are removed automatically.",
        "",
        f"### {total} open roles ({new_today} new today) &nbsp;·&nbsp; {company_count} companies searched",
        "",
        f"<sub>Last updated {last_run_str}</sub>" if last_run_str else "",
        "",
    ]

    for dt in sorted(by_date.keys(), reverse=True):
        jobs = by_date[dt]
        # Sort by first_seen_at descending (newest first); fall back to company name
        jobs.sort(key=lambda j: (j["first_seen_at"] or ""), reverse=True)
        try:
            label = datetime.strptime(dt, "%Y-%m-%d").strftime("%B %-d, %Y")
        except ValueError:
            label = dt
        lines.append("<br>")
        lines.append("")
        lines.append(f"## {label}")
        lines.append("")
        for j in jobs:
            lines.append(f"### [{j['title']}]({j['path']})")
            domain = company_logos.get(j["company"], "")
            logo = f'<img src="https://www.google.com/s2/favicons?domain={domain}&sz=32" width="16" height="16" align="absmiddle">&ensp;' if domain else ""
            lines.append(f"{logo}{j['meta']}")
            if j["summary"]:
                lines.append("")
                lines.append(f"_{j['summary']}_")
            if j["skills"]:
                lines.append("")
                lines.append(" ".join(skill_badge(s) for s in j["skills"]))
            lines.append("")
            ts = j.get("first_seen_at", "")
            if ts:
                try:
                    dt_obj = datetime.fromisoformat(ts)
                    lines.append(f"<sub>{dt_obj.strftime('%B %-d, %Y at %H:%M UTC')}</sub>")
                except ValueError:
                    lines.append(f"<sub>{label}</sub>")
            else:
                lines.append(f"<sub>{label}</sub>")
            lines.append("")
            lines.append("---")
            lines.append("")

    README.write_text("\n".join(lines))
    print(f"Written {README}")


if __name__ == "__main__":
    main()
