import httpx
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
        department = categories.get("department")
        commitment = categories.get("commitment", "")

        remote = "remote" in commitment.lower() if commitment else None

        jobs.append(Job(
            id=f"lever-{slug}-{job_id}",
            company=company,
            company_slug=slug,
            title=item["text"],
            url=item["hostedUrl"],
            source="lever",
            location=location,
            remote=remote,
            departments=[department] if department else [],
        ))

    return jobs
