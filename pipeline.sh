#!/bin/bash
# Daily pipeline: fetch → classify new → render → publish
set -e

SCRAPER_DIR="$(cd "$(dirname "$0")" && pwd)"
JOBS_REPO="$(dirname "$SCRAPER_DIR")/jobs"

cd "$SCRAPER_DIR"

echo "========================================"
echo " Builder Jobs Pipeline — $(date '+%B %-d, %Y')"
echo "========================================"

# 1. Fetch current listings from all companies
echo ""
echo "=== [1/5] Fetching jobs ==="
python3 fetch_jobs.py || echo "  [warn] Some companies failed to fetch — continuing with successful results"

# 2. Fetch Greenhouse descriptions for today's new jobs
echo ""
echo "=== [2/5] Fetching Greenhouse descriptions ==="
python3 fetch_descriptions.py

# 3. Classify only today's new jobs
echo ""
echo "=== [3/5] Classifying new jobs ==="
python3 classify_jobs.py

# 4. Render builder jobs to the builder-jobs repo
echo ""
echo "=== [4/5] Rendering ==="
python3 render.py

# 5. Regenerate README index
echo ""
echo "=== [5/5] Generating index ==="
python3 generate_index.py "$JOBS_REPO"

# 6. Commit and push builder-jobs repo
echo ""
echo "=== Committing builder-jobs ==="
cd "$JOBS_REPO"
if git diff --quiet && git diff --cached --quiet; then
    echo "  No changes to commit in builder-jobs"
else
    git add -A
    git commit -m "$(date '+%B %-d, %Y')"
    git push
fi

# 7. Commit and push scraper repo data
echo ""
echo "=== Committing builder-jobs-scraper ==="
cd "$SCRAPER_DIR"
if git diff --quiet data/ && git diff --cached --quiet data/; then
    echo "  No changes to commit in scraper data"
else
    git add data/jobs_raw.json data/jobs_classified.json data/seen_jobs.json
    git commit -m "Job data — $(date '+%B %-d, %Y')"
    git push
fi

echo ""
echo "========================================"
echo " Done — $(date '+%H:%M:%S')"
echo "========================================"
