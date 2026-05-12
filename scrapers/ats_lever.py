import httpx
from datetime import datetime, timezone
from ._base import Job, ScraperError


BASE_URL = "https://api.lever.co/v0/postings/{slug}"


def scrape(company: str, slug: str) -> list[Job]:
    url = BASE_URL.format(slug=slug)
    try:
        response = httpx.get(url, params={"mode": "json"}, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"Lever request failed for {slug}: {e}") from e

    jobs = []

    for item in response.json():
        job_id = item["id"]
        categories = item.get("categories", {})
        location = categories.get("location")
        department = categories.get("department") or categories.get("team")
        commitment = categories.get("commitment", "")
        remote = "remote" in commitment.lower() if commitment else None

        created_ms = item.get("createdAt")
        posted_at = (
            datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
            if created_ms else None
        )

        raw_text = item.get("descriptionPlain", "").strip()

        jobs.append(Job(
            id=f"lever-{slug}-{job_id}",
            company=company,
            company_slug=slug,
            title=item["text"],
            url=item["hostedUrl"],
            source="lever",
            location=location,
            remote=remote,
            posted_at=posted_at,
            raw_text=raw_text,
        ))

    return jobs
