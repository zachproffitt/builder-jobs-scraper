#!/usr/bin/env python3
"""
Fetch YC companies and add new ones to company_names.txt.

Queries YC's Algolia search index for all active companies, then adds
any not already in company_names.txt. Run discover_companies.py
afterward to detect ATS and update companies.json.

Usage:
    PYTHONPATH=. python tools/discover_yc_companies.py [--dry-run]

    --dry-run   Print what would be added without writing anything.
"""

import json
import re
import sys
from pathlib import Path

import httpx

COMPANY_NAMES_FILE = Path("data/company_names.txt")

# Algolia config embedded in YC's company directory page
ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_INDEX = "YCCompany_production"
YC_COMPANIES_URL = "https://www.ycombinator.com/companies"


def fetch_algolia_api_key(client: httpx.Client) -> str | None:
    """Extract Algolia search API key from YC's company directory page."""
    try:
        resp = client.get(YC_COMPANIES_URL, timeout=15)
        resp.raise_for_status()
        # Key is in: window.AlgoliaOpts = {"app":"45BWZJ1SGC","key":"<key>"}
        m = re.search(r'AlgoliaOpts\s*=\s*\{[^}]*"key"\s*:\s*"([^"]+)"', resp.text)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"Warning: could not fetch YC page to extract API key: {e}")
    return None


def search_algolia(app_id: str, api_key: str, index: str, client: httpx.Client, filters: str = "") -> list[dict]:
    """Search an Algolia index, returning all hits for the given filter."""
    url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index}/query"
    headers = {
        "X-Algolia-Application-Id": app_id,
        "X-Algolia-API-Key": api_key,
    }
    body: dict = {"query": "", "hitsPerPage": 1000}
    if filters:
        body["filters"] = filters

    try:
        resp = client.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception as e:
        print(f"  Algolia search error ({filters!r}): {e}")
        return []


def fetch_all_yc_companies(app_id: str, api_key: str, index: str, client: httpx.Client) -> list[dict]:
    """
    Fetch all YC companies by querying each batch separately.

    Algolia's search API caps at 1000 results per query. Batches max at ~400
    companies each, so paginating by batch gets everything.
    """
    # First get all batch names from facets
    url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index}/query"
    headers = {"X-Algolia-Application-Id": app_id, "X-Algolia-API-Key": api_key}
    try:
        resp = client.post(url, headers=headers, json={
            "query": "", "hitsPerPage": 0, "facets": ["batch"], "maxValuesPerFacet": 200,
        }, timeout=15)
        resp.raise_for_status()
        batches = list(resp.json().get("facets", {}).get("batch", {}).keys())
    except Exception as e:
        print(f"Could not fetch batch list: {e}")
        return []

    print(f"Found {len(batches)} batches — fetching each...")
    seen_ids: set = set()
    companies = []
    for batch in sorted(batches):
        hits = search_algolia(app_id, api_key, index, client, filters=f'batch:"{batch}"')
        new = [h for h in hits if h.get("objectID") not in seen_ids]
        seen_ids.update(h["objectID"] for h in new)
        companies.extend(new)
        print(f"  {batch}: {len(hits)} companies ({len(new)} new)")

    return companies


def load_existing_names() -> set[str]:
    """Load lowercased company names already in company_names.txt."""
    existing = set()
    if not COMPANY_NAMES_FILE.exists():
        return existing
    for line in COMPANY_NAMES_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "|" in line:
            name = line.split("|")[0].strip().lower()
            existing.add(name)
    return existing


def main():
    dry_run = "--dry-run" in sys.argv

    with httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; bot)"},
    ) as client:
        print("Fetching Algolia API key from YC company page...")
        api_key = fetch_algolia_api_key(client)
        if not api_key:
            print("Could not extract API key from page. Try --dry-run to debug.")
            sys.exit(1)
        print(f"Found API key: {api_key[:8]}...")

        print(f"Fetching all companies from Algolia index '{ALGOLIA_INDEX}'...")
        hits = fetch_all_yc_companies(ALGOLIA_APP_ID, api_key, ALGOLIA_INDEX, client)
        print(f"Fetched {len(hits)} total companies from YC")

    existing_names = load_existing_names()

    # Filter: active companies with a website
    candidates = []
    for h in hits:
        name = (h.get("name") or "").strip()
        website = (h.get("website") or "").strip().rstrip("/")
        status = (h.get("status") or "").lower()
        if not name or not website:
            continue
        if status in ("acquired", "inactive", "dead"):
            continue
        # Extract bare domain from website URL
        domain = website.removeprefix("https://").removeprefix("http://").split("/")[0]
        if not domain:
            continue
        candidates.append((name, domain))

    print(f"Active companies with websites: {len(candidates)}")

    new_companies = [
        (name, domain)
        for name, domain in candidates
        if name.lower() not in existing_names
    ]

    print(f"New (not in company_names.txt): {len(new_companies)}")

    if not new_companies:
        print("Nothing to add.")
        return

    # Sort alphabetically and append to company_names.txt
    new_companies.sort(key=lambda x: x[0].lower())

    if dry_run:
        print("\n[dry-run] Would add:")
        for name, domain in new_companies:
            print(f"  {name} | {domain}")
        return

    existing_text = COMPANY_NAMES_FILE.read_text()
    additions = "\n".join(f"{name} | {domain}" for name, domain in new_companies)
    # Ensure file ends with newline before appending
    if existing_text and not existing_text.endswith("\n"):
        existing_text += "\n"
    COMPANY_NAMES_FILE.write_text(existing_text + additions + "\n")
    print(f"\nAdded {len(new_companies)} companies to {COMPANY_NAMES_FILE}")
    print("Run: PYTHONPATH=. python tools/discover_companies.py")


if __name__ == "__main__":
    main()
