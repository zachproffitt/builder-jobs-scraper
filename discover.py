#!/usr/bin/env python3
"""
Discover ATS metadata for companies listed in data/company_names.txt.

For each company not already in data/companies.json, probes Greenhouse,
Lever, and Ashby APIs using candidate slugs derived from the company name.
Found companies are written to companies.json. Unresolved ones are printed
for manual review.

Usage:
    python discover.py
"""

import json
import time
from pathlib import Path

import httpx

NAMES_FILE = Path("data/company_names.txt")
COMPANIES_FILE = Path("data/companies.json")
REQUEST_DELAY = 0.15  # seconds between probes


def candidate_slugs(name: str) -> list[str]:
    """Generate slug candidates from a company name."""
    base = name.lower().strip()

    suffixes = [
        " inc", " corp", " ltd", " llc", " co",
        " technologies", " technology", " systems", " solutions",
        " robotics", " computing", " energy", " ai", " labs",
        " industries", " aerospace", " space", " sciences",
    ]
    for suffix in suffixes:
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip()

    no_space = base.replace(" ", "").replace("-", "").replace(".", "")
    hyphen = base.replace(" ", "-").replace(".", "")
    original = name.lower().replace(" ", "").replace("-", "").replace(".", "")

    seen = set()
    slugs = []
    for s in [no_space, hyphen, original, base]:
        if s and s not in seen:
            slugs.append(s)
            seen.add(s)
    return slugs


def probe_greenhouse(slug: str, client: httpx.Client) -> bool:
    try:
        r = client.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=8,
        )
        return r.status_code == 200 and "jobs" in r.json()
    except Exception:
        return False


def probe_lever(slug: str, client: httpx.Client) -> bool:
    try:
        r = client.get(
            f"https://api.lever.co/v0/postings/{slug}",
            params={"mode": "json"},
            timeout=8,
        )
        return r.status_code == 200 and isinstance(r.json(), list)
    except Exception:
        return False


def probe_ashby(slug: str, client: httpx.Client) -> bool:
    try:
        r = client.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            timeout=8,
        )
        return r.status_code == 200 and "jobs" in r.json()
    except Exception:
        return False


PROBES = [
    ("greenhouse", probe_greenhouse),
    ("lever", probe_lever),
    ("ashby", probe_ashby),
]


def discover_company(name: str, client: httpx.Client) -> "dict | None":
    """Try to find the ATS and slug for a company. Returns None if not found."""
    slugs = candidate_slugs(name)

    for ats, probe in PROBES:
        for slug in slugs:
            time.sleep(REQUEST_DELAY)
            if probe(slug, client):
                return {"name": name, "ats": ats, "slug": slug, "category": []}

    return None


def main():
    names = [
        line.strip()
        for line in NAMES_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    existing: dict[str, dict] = {}
    if COMPANIES_FILE.exists():
        for c in json.loads(COMPANIES_FILE.read_text()):
            existing[c["name"].lower()] = c

    new_names = [n for n in names if n.lower() not in existing]

    if not new_names:
        print(f"All {len(names)} companies already resolved.")
        return

    print(f"Resolving {len(new_names)} new companies ({len(existing)} already known)...")
    print()

    found = []
    unresolved = []

    with httpx.Client() as client:
        for i, name in enumerate(new_names, 1):
            print(f"  [{i:>3}/{len(new_names)}] {name}...", end=" ", flush=True)
            result = discover_company(name, client)
            if result:
                found.append(result)
                existing[name.lower()] = result
                print(f"{result['ats']}/{result['slug']}")
            else:
                unresolved.append(name)
                print("not found")

    COMPANIES_FILE.write_text(
        json.dumps(list(existing.values()), indent=2)
    )

    print(f"\nResolved {len(found)} new companies.")
    print(f"Written to {COMPANIES_FILE}")

    if unresolved:
        print(f"\nNeeds manual review ({len(unresolved)}):")
        for name in unresolved:
            print(f"  - {name}")
        print(
            "\nFor each, find their careers page and add manually to companies.json"
            "\nor add a custom scraper to scrapers/."
        )


if __name__ == "__main__":
    main()
