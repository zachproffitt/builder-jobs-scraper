#!/usr/bin/env python3
"""Write a GitHub Actions step summary for the company discovery run."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SUMMARY_FILE = os.environ.get("GITHUB_STEP_SUMMARY")

SUPPORTED_ATS = {"greenhouse", "lever", "ashby", "smartrecruiters", "bamboo", "breezy", "workable", "workday"}


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    companies_path = DATA_DIR / "companies.json"
    companies = json.loads(companies_path.read_text()) if companies_path.exists() else []

    by_ats: dict[str, int] = {}
    for c in companies:
        ats = c.get("ats", "")
        if ats in SUPPORTED_ATS:
            by_ats[ats] = by_ats.get(ats, 0) + 1

    total_companies = sum(by_ats.values())

    log_path = DATA_DIR / "discovery.log"
    errors = []
    new_added = 0
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            if "ERROR" in line:
                errors.append(line)
            if "Added" in line and "companies" in line:
                # Extract number from "Added N companies to ..."
                parts = line.split("Added")
                if len(parts) > 1:
                    try:
                        n = int(parts[1].strip().split()[0])
                        new_added += n
                    except (ValueError, IndexError):
                        pass

    lines = [
        f"## Company discovery — {now}",
        "",
        f"**{total_companies}** companies tracked &nbsp;·&nbsp; **{new_added}** new this run",
        "",
        "### Companies by ATS",
        "| ATS | Companies |",
        "|---|---|",
    ]
    for ats, count in sorted(by_ats.items(), key=lambda x: -x[1]):
        lines.append(f"| {ats} | {count} |")

    if errors:
        lines += [
            "",
            f"### Errors ({len(errors)})",
            "```",
            *errors[-50:],
            "```",
        ]
    else:
        lines += ["", "No errors."]

    output = "\n".join(lines) + "\n"

    if SUMMARY_FILE:
        with open(SUMMARY_FILE, "a") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
