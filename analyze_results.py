#!/usr/bin/env python3
"""
Analyze classification results from jobs_classified.json.

Reads jobs_classified.json + jobs_raw.json and writes a human-readable
report to logs/analysis_report.txt (and prints to stdout).

Run automatically after classify_jobs.py, or standalone:
    python analyze_results.py
"""

import json
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

JOBS_FILE = Path("data/jobs_raw.json")
CLASSIFIED_FILE = Path("data/jobs_classified.json")
REPORT_FILE = Path("logs/analysis_report.txt")


def main():
    REPORT_FILE.parent.mkdir(exist_ok=True)

    if not CLASSIFIED_FILE.exists():
        print("data/jobs_classified.json not found — run classify_jobs.py first.")
        return

    jobs_raw = json.loads(JOBS_FILE.read_text())
    classified = json.loads(CLASSIFIED_FILE.read_text())

    jobs_by_id = {j["id"]: j for j in jobs_raw}

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit(f"Classification Analysis Report")
    emit(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    emit("=" * 60)

    # --- Overall counts ---
    total = len(classified)
    builders = [jid for jid, v in classified.items() if v.get("is_engineering") is True]
    not_builders = [jid for jid, v in classified.items() if v.get("is_engineering") is False]
    unclear = [jid for jid, v in classified.items() if v.get("is_engineering") is None]
    no_desc = sum(1 for j in jobs_raw if not j.get("raw_text", "").strip())

    emit(f"\nOVERALL")
    emit(f"  Total classified:  {total:>6}")
    emit(f"  Builder (yes):     {len(builders):>6}  ({len(builders)/total*100:.1f}%)")
    emit(f"  Not builder (no):  {len(not_builders):>6}  ({len(not_builders)/total*100:.1f}%)")
    emit(f"  Unclear:           {len(unclear):>6}  ({len(unclear)/total*100:.1f}%)")
    emit(f"  Skipped (no desc): {no_desc:>6}")

    # --- By source ---
    emit(f"\nBY SOURCE")
    by_source = defaultdict(lambda: {"yes": 0, "no": 0, "unclear": 0})
    for jid, v in classified.items():
        job = jobs_by_id.get(jid)
        if not job:
            continue
        src = job.get("source", "unknown")
        result = "yes" if v.get("is_engineering") is True else ("no" if v.get("is_engineering") is False else "unclear")
        by_source[src][result] += 1

    for src, counts in sorted(by_source.items()):
        total_src = sum(counts.values())
        emit(f"  {src:<12}  builders={counts['yes']:>4}  not={counts['no']:>4}  unclear={counts['unclear']:>4}  total={total_src}")

    # --- Builders per company (top 25) ---
    emit(f"\nBUILDER JOBS BY COMPANY (top 25)")
    company_builders = Counter()
    for jid in builders:
        job = jobs_by_id.get(jid)
        if job:
            company_builders[job["company"]] += 1

    for company, count in company_builders.most_common(25):
        emit(f"  {count:>4}  {company}")

    # --- High unclear rate by company ---
    emit(f"\nHIGH UNCLEAR RATE (>25%, min 10 jobs classified)")
    company_counts = defaultdict(lambda: {"yes": 0, "no": 0, "unclear": 0})
    for jid, v in classified.items():
        job = jobs_by_id.get(jid)
        if not job:
            continue
        result = "yes" if v.get("is_engineering") is True else ("no" if v.get("is_engineering") is False else "unclear")
        company_counts[job["company"]][result] += 1

    flagged = []
    for company, counts in company_counts.items():
        total_co = sum(counts.values())
        if total_co >= 10 and counts["unclear"] / total_co > 0.25:
            flagged.append((counts["unclear"] / total_co, company, counts))
    flagged.sort(reverse=True)

    if flagged:
        for rate, company, counts in flagged:
            emit(f"  {rate*100:.0f}% unclear  {company}  (yes={counts['yes']} no={counts['no']} unclear={counts['unclear']})")
    else:
        emit("  None")

    # --- Sample: 15 random builder jobs ---
    random.seed(42)
    emit(f"\nSAMPLE BUILDER JOBS (15 random)")
    sample_builders = random.sample(builders, min(15, len(builders)))
    for jid in sample_builders:
        job = jobs_by_id.get(jid)
        v = classified[jid]
        if not job:
            continue
        summary = v.get("job_summary") or "no summary"
        emit(f"  ✓  {job['company']}: {job['title']}")
        emit(f"     → {summary[:100]}")

    # --- Sample: 15 random non-builder decisions ---
    emit(f"\nSAMPLE NON-BUILDER DECISIONS (15 random — verify these look correct)")
    sample_not = random.sample(not_builders, min(15, len(not_builders)))
    for jid in sample_not:
        job = jobs_by_id.get(jid)
        if not job:
            continue
        emit(f"  ✗  {job['company']}: {job['title']}")

    # --- Sample: unclear cases ---
    emit(f"\nSAMPLE UNCLEAR CASES (10 random — these won't be rendered)")
    sample_unclear = random.sample(unclear, min(10, len(unclear)))
    for jid in sample_unclear:
        job = jobs_by_id.get(jid)
        if not job:
            continue
        emit(f"  ?  {job['company']}: {job['title']}")

    emit(f"\n{'=' * 60}")
    emit(f"Report written to {REPORT_FILE}")

    REPORT_FILE.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
