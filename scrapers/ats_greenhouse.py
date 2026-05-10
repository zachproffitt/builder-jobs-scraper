import httpx
from ._base import Job, ScraperError


BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
JOB_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"


def scrape(company: str, slug: str) -> list[Job]:
    url = BASE_URL.format(slug=slug)
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"Greenhouse request failed for {slug}: {e}") from e

    data = response.json()
    jobs = []

    for item in data.get("jobs", []):
        job_id = str(item["id"])
        location = item.get("location", {}).get("name")
        departments = [d["name"] for d in item.get("departments", []) if d.get("name")]

        jobs.append(Job(
            id=f"greenhouse-{slug}-{job_id}",
            company=company,
            company_slug=slug,
            title=item["title"],
            url=item["absolute_url"],
            source="greenhouse",
            location=location,
            departments=departments,
        ))

    return jobs
