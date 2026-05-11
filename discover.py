#!/usr/bin/env python3
"""
Discover ATS metadata for companies listed in data/company_names.txt.

Each line in company_names.txt must be:  Company Name | domain.com
The domain is used to scrape the company's careers page and find the ATS.

For each company not already in data/companies.json, fetches the careers
page at domain/careers (and variations), follows redirects, and extracts
the ATS slug from greenhouse.io, lever.co, or ashbyhq.com URLs.

Also scrapes domain/about for a company description stored in companies.json.

Usage:
    python discover.py             # resolve new companies only
    python discover.py --recheck   # also re-verify and fix existing entries

Results are written to data/companies.json.
Errors and unresolved companies are logged to logs/discover.log.

Note: If discover.py picks the wrong slug (e.g. for companies with ambiguous
names), edit data/companies.json directly. That entry is skipped on future runs.
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

NAMES_FILE = Path("data/company_names.txt")
COMPANIES_FILE = Path("data/companies.json")
LOG_FILE = Path("logs/discover.log")
REQUEST_DELAY = 0.2

CAREERS_PATHS = ["/careers", "/jobs", "/careers/", "/jobs/", "/work-with-us", "/join"]
ABOUT_PATHS = ["/about", "/about-us", "/company", "/who-we-are"]

# Greenhouse embed URLs: boards.greenhouse.io/embed/job_board?for=slug
#   or the JS variant:   boards.greenhouse.io/embed/job_board/js?for=slug
_GH_EMBED = re.compile(r"greenhouse\.io/embed[^?]*\?for=([A-Za-z0-9_-]+)", re.I)
_GH_BOARD = re.compile(r"(?:boards|job-boards(?:\.eu)?)\.greenhouse\.io/([A-Za-z0-9_-]+)", re.I)
# Slugs that are generic page names, not real ATS board IDs
_SLUG_BLACKLIST = {"embed", "job_board", "jobs", "careers", "apply", "boards"}

ATS_PATTERNS = [
    (_GH_EMBED, "greenhouse"),
    (_GH_BOARD, "greenhouse"),
    (re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.+-]+)", re.I), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.+-]+)", re.I), "ashby"),
]


def parse_names_file() -> list[tuple[str, str]]:
    """Parse company_names.txt, return list of (name, domain) tuples."""
    entries = []
    for line in NAMES_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"  WARNING: malformed line (missing domain): {line!r}")
            continue
        name, _, domain = line.partition("|")
        name = name.strip()
        domain = domain.strip()
        if not name or not domain or domain == "???":
            print(f"  WARNING: missing domain for {name!r} — skipping")
            continue
        entries.append((name, domain))
    return entries


def extract_ats(text: str) -> "tuple[str, str] | None":
    """Search text for any ATS URL and return (ats, slug) or None."""
    for pattern, ats in ATS_PATTERNS:
        m = pattern.search(text)
        if m:
            slug = m.group(1)
            if slug.lower() not in _SLUG_BLACKLIST:
                return ats, slug
    return None


def scrape_careers(domain: str, client: httpx.Client) -> "tuple[str, str] | None":
    """
    Try to find ATS info by fetching the company's careers page.
    Returns (ats, slug) or None.
    """
    base = f"https://{domain}"

    for path in CAREERS_PATHS:
        time.sleep(REQUEST_DELAY)
        try:
            r = client.get(base + path, timeout=10, follow_redirects=True)
        except Exception:
            continue

        # Check the final URL (after redirects)
        result = extract_ats(str(r.url))
        if result:
            return result

        # Check page HTML
        if r.status_code == 200:
            result = extract_ats(r.text)
            if result:
                return result

    return None


def scrape_about(domain: str, client: httpx.Client) -> str:
    """
    Fetch the company's about page and return visible text (up to 3000 chars).
    Returns empty string on failure.
    """
    base = f"https://{domain}"

    for path in ABOUT_PATHS:
        time.sleep(REQUEST_DELAY)
        try:
            r = client.get(base + path, timeout=10, follow_redirects=True)
            if r.status_code != 200:
                continue
            # Strip HTML tags and collapse whitespace
            text = re.sub(r"<script[^>]*>.*?</script>", " ", r.text, flags=re.S)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 200:
                return text[:3000]
        except Exception:
            continue

    return ""


def verify_entry(company: dict, client: httpx.Client) -> bool:
    """Check if the current ATS/slug is still valid."""
    ats = company.get("ats")
    slug = company.get("slug")
    if not ats or not slug:
        return False

    time.sleep(REQUEST_DELAY)
    try:
        if ats == "greenhouse":
            r = client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=8
            )
            return r.status_code == 200 and "jobs" in r.json()
        elif ats == "lever":
            r = client.get(
                f"https://api.lever.co/v0/postings/{slug}",
                params={"mode": "json"},
                timeout=8,
            )
            return r.status_code == 200 and isinstance(r.json(), list)
        elif ats == "ashby":
            r = client.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=8
            )
            return r.status_code == 200 and "jobs" in r.json()
    except Exception:
        pass
    return False


def main():
    recheck = "--recheck" in sys.argv
    LOG_FILE.parent.mkdir(exist_ok=True)

    entries = parse_names_file()  # [(name, domain), ...]
    name_domain = {name: domain for name, domain in entries}

    existing: dict[str, dict] = {}
    if COMPANIES_FILE.exists():
        for c in json.loads(COMPANIES_FILE.read_text()):
            existing[c["name"].lower()] = c

    changed = False
    log_lines = [f"=== discover.py {datetime.now().strftime('%Y-%m-%d %H:%M')} ==="]
    fixed = []
    still_broken = []
    newly_found = []
    unresolved = []

    with httpx.Client(follow_redirects=True) as client:

        # --- Recheck: verify and fix existing entries ---
        if recheck:
            to_check = list(existing.items())
            print(f"Rechecking {len(to_check)} existing companies...")
            print()

            for i, (key, company) in enumerate(to_check, 1):
                label = f"{company['name']} ({company.get('ats','?')}/{company.get('slug','?')})"
                print(f"  [{i:>3}/{len(to_check)}] {label[:65]}", end=" ", flush=True)

                if verify_entry(company, client):
                    print("ok")
                    continue

                # Try to re-scrape via domain
                domain = name_domain.get(company["name"])
                if not domain:
                    print("broken (no domain)")
                    still_broken.append(company["name"])
                    continue

                result = scrape_careers(domain, client)
                if result:
                    ats, slug = result
                    old = f"{company.get('ats')}/{company.get('slug')}"
                    new = f"{ats}/{slug}"
                    company["ats"] = ats
                    company["slug"] = slug
                    existing[key] = company
                    fixed.append((company["name"], old, new))
                    changed = True
                    print(f"FIXED -> {new}")
                else:
                    still_broken.append(company["name"])
                    print("still broken")

            print(f"\nFixed {len(fixed)}, still broken: {len(still_broken)}\n")

        # --- Discover new companies ---
        new_entries = [(n, d) for n, d in entries if n.lower() not in existing]

        if not new_entries:
            print(f"All {len(entries)} companies already resolved.")
        else:
            print(f"Resolving {len(new_entries)} new companies ({len(existing)} already known)...")
            print()

            for i, (name, domain) in enumerate(new_entries, 1):
                print(f"  [{i:>3}/{len(new_entries)}] {name} ({domain})...", end=" ", flush=True)

                result = scrape_careers(domain, client)
                if result:
                    ats, slug = result
                    about = scrape_about(domain, client)
                    entry = {
                        "name": name,
                        "ats": ats,
                        "slug": slug,
                        "website": f"https://{domain}",
                        "category": [],
                    }
                    if about:
                        entry["about_text"] = about
                    existing[name.lower()] = entry
                    newly_found.append(name)
                    changed = True
                    print(f"{ats}/{slug}")
                else:
                    unresolved.append((name, domain))
                    print("not found")

        print(f"\nResolved {len(newly_found)} new companies.")

        if unresolved:
            print(f"\nNeeds manual review ({len(unresolved)}):")
            for name, domain in unresolved:
                print(f"  - {name} ({domain})")
            print("\nCheck the careers page manually and add to data/companies.json.")

    # Write updated companies.json
    if changed:
        COMPANIES_FILE.write_text(json.dumps(list(existing.values()), indent=2))
        print(f"\nWritten to {COMPANIES_FILE}")

    # Write log
    if recheck and fixed:
        log_lines.append(f"\nFixed {len(fixed)} slugs:")
        for name, old, new in fixed:
            log_lines.append(f"  {name}: {old} -> {new}")

    if still_broken:
        log_lines.append(f"\nStill broken ({len(still_broken)}) — needs manual review:")
        for name in still_broken:
            log_lines.append(f"  - {name}")

    if unresolved:
        log_lines.append(f"\nUnresolved new companies ({len(unresolved)}):")
        for name, domain in unresolved:
            log_lines.append(f"  - {name} ({domain})")

    log_lines.append("")
    LOG_FILE.write_text("\n".join(log_lines))
    print(f"Log written to {LOG_FILE}")


if __name__ == "__main__":
    main()
