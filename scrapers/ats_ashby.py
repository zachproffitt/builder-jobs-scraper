import httpx
from ._base import Job, ScraperError


BASE_URL = "https://api.ashbyhq.com/posting-public/job-board/{slug}"


def scrape(company: str, slug: str) -> list[Job]:
    url = BASE_URL.format(slug=slug)
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"Ashby request failed for {slug}: {e}") from e

    data = response.json()
    jobs = []

    for item in data.get("jobPostings", []):
        job_id = item["id"]
        location = item.get("locationName")
        department = item.get("departmentName")
        remote = item.get("isRemote")

        jobs.append(Job(
            id=f"ashby-{slug}-{job_id}",
            company=company,
            company_slug=slug,
            title=item["title"],
            url=item["jobPostingUrl"],
            source="ashby",
            location=location,
            remote=remote,
            departments=[department] if department else [],
        ))

    return jobs
