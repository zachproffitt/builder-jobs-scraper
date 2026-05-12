from datetime import datetime, timezone

import httpx

from ._base import Job, ScraperError

BASE_URL = "https://api.lever.co/v0/postings/{slug}"


def scrape(company: str, slug: str) -> list[Job]:
    try:
        response = httpx.get(BASE_URL.format(slug=slug), params={"mode": "json"}, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"Lever request failed for {slug}: {e}") from e

    jobs = []
    for item in response.json():
        categories = item.get("categories", {})
        commitment = categories.get("commitment", "")
        created_ms = item.get("createdAt")

        jobs.append(Job(
            id=f"lever-{slug}-{item['id']}",
            company=company,
            company_slug=slug,
            title=item["text"],
            url=item["hostedUrl"],
            source="lever",
            location=categories.get("location"),
            remote="remote" in commitment.lower() if commitment else None,
            posted_at=datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).date() if created_ms else None,
            raw_text=item.get("descriptionPlain", "").strip(),
        ))

    return jobs
