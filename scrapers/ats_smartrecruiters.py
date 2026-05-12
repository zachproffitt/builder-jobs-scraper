import html
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from ._base import Job, ScraperError

LIST_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
DETAIL_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{job_id}"
WORKERS = 8

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>|</li>|</h[1-6]>", "\n", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    lines = [l.strip() for l in text.splitlines()]
    text = "\n".join(l for l in lines if l)
    return _WHITESPACE_RE.sub("\n\n", text).strip()


def parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def fetch_description(slug: str, job_id: str) -> str | None:
    try:
        r = httpx.get(DETAIL_URL.format(slug=slug, job_id=job_id), timeout=15)
        r.raise_for_status()
        sections = r.json().get("jobAd", {}).get("sections", {})
        text = sections.get("jobDescription", {}).get("text", "")
        return html_to_text(text) if text else None
    except Exception:
        return None


def scrape(company: str, slug: str) -> list[Job]:
    try:
        r = httpx.get(LIST_URL.format(slug=slug), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"SmartRecruiters request failed for {slug}: {e}") from e

    items = r.json().get("content", [])
    if not items:
        return []

    # Fetch all descriptions concurrently
    descriptions: dict[str, str | None] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(fetch_description, slug, item["id"]): item["id"]
            for item in items
        }
        for future in as_completed(futures):
            job_id = futures[future]
            descriptions[job_id] = future.result()

    jobs = []
    for item in items:
        loc = item.get("location", {})
        city = loc.get("city", "")
        country = loc.get("country", "")
        remote = loc.get("remote")
        location_parts = [p for p in [city, country] if p]
        location = ", ".join(location_parts) or None

        jobs.append(Job(
            id=f"smartrecruiters-{slug}-{item['id']}",
            company=company,
            company_slug=slug,
            title=item["name"],
            url=item.get("ref", f"https://jobs.smartrecruiters.com/{slug}/{item['id']}"),
            source="smartrecruiters",
            location=location,
            remote=remote if isinstance(remote, bool) else None,
            posted_at=parse_date(item.get("releasedDate")),
            raw_text=descriptions.get(item["id"]),
        ))

    return jobs
