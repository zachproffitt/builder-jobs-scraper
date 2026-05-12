#!/usr/bin/env python3
"""
Set up a synthetic test dataset spanning 15 days to verify the full pipeline.

Selects a random sample of existing jobs, distributes them across the last
15 days (so day-15 falls outside the 14-day rolling window and should be
dropped), marks all other jobs as old in seen_jobs.json so they never appear
as new, then clears jobs_classified.json for a clean classify run.

After running this script:
    python3 fetch_jobs.py           # re-fetches; non-test jobs drop off
    python3 fetch_descriptions.py --all  # get Greenhouse descriptions for test jobs
    python3 classify_jobs.py --all  # classify all test jobs
    python3 render.py
    python3 generate_index.py ../jobs
"""

import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path("data")
JOBS_FILE = DATA_DIR / "jobs_raw.json"
SEEN_FILE = DATA_DIR / "seen_jobs.json"
CLASSIFIED_FILE = DATA_DIR / "jobs_classified.json"

DAYS = 16          # today-15 through today; day-15 is outside the 14-day window
JOBS_PER_DAY = 12  # ~10 survive per day after builder filtering (~30-40% hit rate)
OLD_DATE = (date.today() - timedelta(days=30)).isoformat()


def main():
    jobs = json.loads(JOBS_FILE.read_text())
    seen = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}

    # Separate by source for balanced sampling
    by_source = defaultdict(list)
    for j in jobs:
        by_source[j.get("source", "unknown")].append(j)

    print(f"Available: {sum(len(v) for v in by_source.values())} jobs")
    for src, lst in sorted(by_source.items()):
        print(f"  {src}: {len(lst)}")

    # Sample evenly from each source
    total_needed = DAYS * JOBS_PER_DAY
    per_source = total_needed // len(by_source)
    selected = []
    for src, lst in by_source.items():
        n = min(per_source, len(lst))
        selected.extend(random.sample(lst, n))

    # Trim/top-up to exact total
    random.shuffle(selected)
    selected = selected[:total_needed]

    print(f"\nSelected {len(selected)} jobs for test dataset")

    # Assign first_seen dates: spread evenly from today-15 to today
    today = date.today()
    assigned = {}
    for i, job in enumerate(selected):
        day_offset = DAYS - 1 - (i % DAYS)   # today-15 down to today-0
        first_seen = (today - timedelta(days=day_offset)).isoformat()
        assigned[job["id"]] = first_seen

    # Count per day
    from collections import Counter
    day_counts = Counter(assigned.values())
    print("\nJobs per day:")
    for d in sorted(day_counts):
        marker = " ← outside window (will be dropped)" if d < (today - timedelta(days=14)).isoformat() else ""
        print(f"  {d}: {day_counts[d]}{marker}")

    # Update seen_jobs.json:
    # - test jobs get their assigned date
    # - all others get OLD_DATE so they age out immediately and never appear as new
    new_seen = {job_id: OLD_DATE for job_id in seen}
    new_seen.update(assigned)
    SEEN_FILE.write_text(json.dumps(new_seen, indent=2))
    print(f"\nUpdated seen_jobs.json: {len(assigned)} test jobs, {len(new_seen) - len(assigned)} marked old")

    # Update jobs_raw.json to only contain test jobs with their assigned dates
    for job in selected:
        job["first_seen"] = assigned[job["id"]]
    JOBS_FILE.write_text(json.dumps(selected, indent=2))
    print(f"Updated jobs_raw.json: {len(selected)} test jobs")

    # Clear classifications for a clean run
    CLASSIFIED_FILE.write_text("{}")
    print("Cleared jobs_classified.json")

    print("\nNext steps:")
    print("  python3 fetch_jobs.py           # rolling window drops day-15 jobs")
    print("  python3 fetch_descriptions.py --all  # Greenhouse descriptions")
    print("  python3 classify_jobs.py --all  # classify all test jobs")
    print("  python3 render.py")
    print("  python3 generate_index.py ../jobs")


if __name__ == "__main__":
    main()
