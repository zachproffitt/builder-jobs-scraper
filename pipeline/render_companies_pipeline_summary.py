#!/usr/bin/env python3
"""Write a GitHub Actions step summary for the company discovery run."""

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from render_common import SUPPORTED_ATS, write_step_summary

DATA_DIR = Path(__file__).parent.parent / "data"


def parse_log(log_path: Path) -> dict:
    """Extract key counts from companies.log."""
    stats = {
        "yc_new": 0,
        "vc_new": 0,
        "industry_new": 0,
        "resolved_supported": 0,
        "resolved_detected": 0,
        "not_found": 0,
        "errors": [],
    }
    if not log_path.exists():
        return stats

    for line in log_path.read_text().splitlines():
        if "[yc]" in line and "New:" in line:
            m = re.search(r"New:\s*(\d+)", line)
            if m:
                stats["yc_new"] = int(m.group(1))
        elif "[vc]" in line and "Total new companies" in line:
            m = re.search(r"Total new companies across all VCs:\s*(\d+)", line)
            if m:
                stats["vc_new"] = int(m.group(1))
        elif "[industry]" in line and "Total new companies:" in line:
            m = re.search(r"Total new companies:\s*(\d+)", line)
            if m:
                stats["industry_new"] = int(m.group(1))
        elif "[ats]" in line and "Resolved:" in line:
            m = re.search(r"Resolved:\s*(\d+) supported,\s*(\d+) detected[^,]*,\s*(\d+) not found", line)
            if m:
                stats["resolved_supported"] = int(m.group(1))
                stats["resolved_detected"] = int(m.group(2))
                stats["not_found"] = int(m.group(3))
        elif "ERROR" in line:
            stats["errors"].append(line)

    return stats


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    companies_path = DATA_DIR / "companies.json"
    companies = json.loads(companies_path.read_text()) if companies_path.exists() else []

    by_ats: dict[str, int] = {}
    by_status: Counter = Counter()
    for c in companies:
        by_status[c.get("status", "unknown")] += 1
        ats = c.get("ats", "")
        if ats in SUPPORTED_ATS and c.get("status") == "active":
            by_ats[ats] = by_ats.get(ats, 0) + 1

    total_active = sum(by_ats.values())

    log_path = DATA_DIR / "companies.log"
    s = parse_log(log_path)

    total_new_stubs = s["yc_new"] + s["vc_new"] + s["industry_new"]
    total_processed = s["resolved_supported"] + s["resolved_detected"] + s["not_found"]

    lines = [
        f"## Company discovery — {now}",
        "",
        f"**{total_active}** companies with supported ATS &nbsp;·&nbsp; **{total_new_stubs}** new stubs discovered",
        "",
    ]

    if total_new_stubs:
        lines += [
            "### Discovery",
            "| Source | New companies |",
            "|---|---|",
            f"| YC | {s['yc_new']} |",
            f"| VC portfolios | {s['vc_new']} |",
            f"| Industry curation | {s['industry_new']} |",
            f"| **Total** | **{total_new_stubs}** |",
            "",
        ]

    if total_processed:
        resolve_rate = f"{s['resolved_supported'] / total_processed * 100:.1f}%" if total_processed else "—"
        lines += [
            "### ATS resolution",
            "| Result | Count |",
            "|---|---|",
            f"| Resolved (supported ATS) | **{s['resolved_supported']}** |",
            f"| Resolved (no scraper yet) | {s['resolved_detected']} |",
            f"| Not found | {s['not_found']} |",
            f"| Resolution rate | {resolve_rate} |",
            "",
        ]

    lines += [
        "### All companies by ATS",
        "| ATS | Companies |",
        "|---|---|",
    ]
    for ats, count in sorted(by_ats.items(), key=lambda x: -x[1]):
        lines.append(f"| {ats} | {count} |")

    lines += [
        "",
        "### Database totals",
        "| Status | Count |",
        "|---|---|",
        f"| Active (supported ATS) | {by_status.get('active', 0)} |",
        f"| Detected (no scraper) | {by_status.get('detected', 0)} |",
        f"| No ATS found | {by_status.get('no_ats', 0)} |",
        "",
    ]

    if s["errors"]:
        lines += [
            f"### Errors ({len(s['errors'])})",
            "```",
            *s["errors"][-50:],
            "```",
        ]
    else:
        lines += ["No errors."]

    write_step_summary("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
