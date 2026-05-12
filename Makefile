.PHONY: run fetch describe describe-all classify classify-all render index discover

JOBS_REPO ?= ../jobs

run:
	bash pipeline.sh

fetch:
	python3 fetch_jobs.py

describe:
	python3 fetch_job_descriptions.py

describe-all:
	python3 fetch_job_descriptions.py --all

classify:
	python3 classify_jobs.py

classify-all:
	python3 classify_jobs.py --all

render:
	python3 render_jobs.py

index:
	python3 generate_index.py $(JOBS_REPO)

discover:
	python3 discover_companies.py
