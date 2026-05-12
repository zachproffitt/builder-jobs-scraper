import re
import httpx
from ._base import Job, ScraperError


BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

# Only match patterns where "remote" is an explicit signal, not inferred.
# "Remote" alone, with a region qualifier, or as one of multiple options.
_REMOTE_RE = re.compile(r"\bremote\b", re.I)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.I)


def infer_remote(location: str | None) -> bool | None:
    if not location:
        return None
    if _REMOTE_RE.search(location):
        return True
    if _HYBRID_RE.search(location):
        return None  # hybrid — don't claim remote
    return None  # can't tell from location alone


def scrape(company: str, slug: str) -> list[Job]:
    url = BASE_URL.format(slug=slug)
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"Greenhouse request failed for {slug}: {e}") from e

    jobs = []

    for item in response.json().get("jobs", []):
        location = item.get("location", {}).get("name")
        jobs.append(Job(
            id=f"greenhouse-{slug}-{item['id']}",
            company=company,
            company_slug=slug,
            title=item["title"],
            url=item["absolute_url"],
            source="greenhouse",
            location=location,
            remote=infer_remote(location),
        ))

    return jobs
