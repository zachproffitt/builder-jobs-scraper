import httpx
from datetime import datetime, timezone
from ._base import Job, ScraperError


BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def scrape(company: str, slug: str) -> list[Job]:
    url = BASE_URL.format(slug=slug)
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"Ashby request failed for {slug}: {e}") from e

    jobs = []

    for item in response.json().get("jobs", []):
        published = item.get("publishedAt")
        try:
            posted_at = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
        except (ValueError, AttributeError):
            posted_at = None

        jobs.append(Job(
            id=f"ashby-{slug}-{item['id']}",
            company=company,
            company_slug=slug,
            title=item["title"],
            url=item["jobUrl"],
            source="ashby",
            location=item.get("location"),
            remote=item.get("isRemote"),
            posted_at=posted_at,
            raw_text=item.get("descriptionPlain", ""),
        ))

    return jobs
