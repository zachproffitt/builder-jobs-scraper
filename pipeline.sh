#!/bin/bash
# Daily pipeline: discover → fetch → describe → classify → render → publish
set -e

SCRAPER_DIR="$(cd "$(dirname "$0")" && pwd)"
JOBS_REPO="$(dirname "$SCRAPER_DIR")/jobs"
export PYTHONPATH="$SCRAPER_DIR"

cd "$SCRAPER_DIR"

mkdir -p logs

LOG_FILE="$SCRAPER_DIR/logs/pipeline.log"

# Tee everything (stdout + stderr) to the log file for the rest of the script
exec > >(tee -a "$LOG_FILE") 2>&1

step() {
    echo ""
    echo "========================================"
    echo " $1"
    echo " $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
}

step "Builder Jobs Pipeline starting"

# 1. Discover ATS for any new companies added to company_names.txt
step "[1/6] Discovering companies"
python3 tools/discover_companies.py

# 2. Fetch current listings from all companies
step "[2/6] Fetching jobs"
python3 pipeline/fetch_jobs.py || echo "  [warn] Some companies failed — continuing"

# 3. Fetch Greenhouse descriptions for today's new jobs
step "[3/6] Fetching descriptions"
python3 pipeline/fetch_job_descriptions.py

# 4. Classify only today's new jobs
step "[4/6] Classifying"
if ! pgrep -x ollama > /dev/null; then
    echo "  ERROR: Ollama is not running. Start it with: ollama serve"
    exit 1
fi
python3 pipeline/classify_jobs.py

# 5. Render builder jobs to the builder-jobs repo
step "[5/6] Rendering"
python3 pipeline/render_jobs.py

# 6. Regenerate README index
step "[6/6] Generating index"
python3 pipeline/generate_index.py "$JOBS_REPO"

# Commit and push builder-jobs repo
step "Committing builder-jobs"
cd "$JOBS_REPO"
if git diff --quiet && git diff --cached --quiet; then
    echo "  No changes to commit in builder-jobs"
else
    git add -A
    git commit -m "$(date '+%B %-d, %Y')"
    git push
fi

# Commit and push scraper repo data
step "Committing builder-jobs-scraper"
cd "$SCRAPER_DIR"
if git diff --quiet data/ && git diff --cached --quiet data/; then
    echo "  No changes to commit in scraper data"
else
    git add data/jobs_raw.json data/jobs_classified.json data/seen_jobs.json data/companies.json
    git commit -m "Job data — $(date '+%B %-d, %Y')"
    git push
fi

step "Done"
echo "  Log: $LOG_FILE"
