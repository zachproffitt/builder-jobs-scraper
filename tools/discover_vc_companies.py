#!/usr/bin/env python3
"""
Fetch portfolio companies from VC firms and add new ones to company_names.txt.

Each VC uses a different scraping strategy depending on what their site exposes.
Run discover_companies.py afterward to detect ATS and update companies.json.

Usage:
    PYTHONPATH=. python tools/discover_vc_companies.py [--dry-run]

    --dry-run   Print what would be added without writing anything.

Supported VCs:
    Founders Fund   — WordPress REST API (company post type)
    Khosla Ventures — img alt + href pairs on portfolio page

TODO (needs better name extraction — og:title returns marketing slogans):
    Greylock, a16z, Sequoia, Bessemer, Lightspeed
    Options: Playwright rendering, or Claude to clean up og:title strings.
"""

import re
import sys
from pathlib import Path

import httpx

COMPANY_NAMES_FILE = Path("data/company_names.txt")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

NOISE_DOMAINS = {
    "cdn", "fonts", "google", "twitter", "linkedin", "facebook",
    "instagram", "youtube", "gmpg", "w3.org", "schema.org",
    "wp-content", "welanded", "gravatar", "cloudflare",
}


def is_noise_url(url: str) -> bool:
    return any(n in url for n in NOISE_DOMAINS)


def clean_domain(url: str) -> str:
    return url.removeprefix("https://").removeprefix("http://").lstrip("/").split("/")[0].lstrip("www.")



# ---------------------------------------------------------------------------
# VC scrapers — each returns list of (name, domain)
# ---------------------------------------------------------------------------

def scrape_founders_fund(client: httpx.Client) -> list[tuple[str, str]]:
    """Fetch via WordPress REST API. Names only — domains guessed from slug."""
    results = []
    page = 1
    total = None
    while True:
        r = client.get(
            f"https://foundersfund.com/wp-json/wp/v2/company?per_page=100&page={page}&_fields=title,slug",
            timeout=15,
        )
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        if total is None:
            total = int(r.headers.get("X-WP-Total", 0))
        for c in data:
            name = c.get("title", {}).get("rendered", "").strip()
            slug = c.get("slug", "").strip()
            if name and slug:
                # Try slug as domain; discover_companies.py will verify/fix
                domain = f"{slug}.com"
                results.append((name, domain))
        page += 1
        if len(results) >= (total or 999):
            break
    print(f"  Founders Fund: {len(results)} companies")
    return results


def scrape_khosla(client: httpx.Client) -> list[tuple[str, str]]:
    """Extract img alt + href pairs from portfolio page."""
    r = client.get("https://www.khoslaventures.com/portfolio", timeout=15, follow_redirects=True)
    r.raise_for_status()
    pairs = re.findall(
        r'<a[^>]+href="(https?://(?!(?:www\.)?khosla)[^"]+)"[^>]*>\s*<(?:img|figure)[^>]*alt="([^"]{2,60})"',
        r.text,
    )
    results = []
    for url, name in pairs:
        if is_noise_url(url):
            continue
        name = name.strip()
        domain = clean_domain(url)
        if name and domain and name.lower() != "icon link":
            results.append((name, domain))
    print(f"  Khosla Ventures: {len(results)} companies")
    return results


VC_SCRAPERS = [
    ("Founders Fund", scrape_founders_fund),
    ("Khosla Ventures", scrape_khosla),
]


# ---------------------------------------------------------------------------

def load_existing(file: Path) -> tuple[set[str], set[str]]:
    """Return (existing_names_lower, existing_domains_lower)."""
    names, domains = set(), set()
    if not file.exists():
        return names, domains
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        name, _, domain = line.partition("|")
        names.add(name.strip().lower())
        domains.add(domain.strip().lower().lstrip("www."))
    return names, domains


def main():
    dry_run = "--dry-run" in sys.argv
    existing_names, existing_domains = load_existing(COMPANY_NAMES_FILE)

    all_new: list[tuple[str, str]] = []

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for vc_name, scraper in VC_SCRAPERS:
            print(f"\nScraping {vc_name}...")
            try:
                companies = scraper(client)
            except Exception as e:
                print(f"  ERROR: {e}")
                continue

            for name, domain in companies:
                domain_bare = domain.lower().lstrip("www.")
                if name.lower() in existing_names or domain_bare in existing_domains:
                    continue
                all_new.append((name, domain))
                existing_names.add(name.lower())
                existing_domains.add(domain_bare)

    all_new.sort(key=lambda x: x[0].lower())
    print(f"\nTotal new companies across all VCs: {len(all_new)}")

    if not all_new:
        print("Nothing to add.")
        return

    if dry_run:
        print("\n[dry-run] Would add:")
        for name, domain in all_new:
            print(f"  {name} | {domain}")
        return

    existing_text = COMPANY_NAMES_FILE.read_text()
    if existing_text and not existing_text.endswith("\n"):
        existing_text += "\n"
    additions = "\n".join(f"{name} | {domain}" for name, domain in all_new)
    COMPANY_NAMES_FILE.write_text(existing_text + additions + "\n")
    print(f"Added {len(all_new)} companies to {COMPANY_NAMES_FILE}")
    print("Run: PYTHONPATH=. python tools/discover_companies.py")


if __name__ == "__main__":
    main()
