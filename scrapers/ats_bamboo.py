from datetime import date

import httpx

from ._base import Job, ScraperError

LIST_URL = "https://{slug}.bamboohr.com/careers/list"

# locationType: "0" = on-site, "2" = remote; anything else is unclear
_REMOTE_TYPES = {"2"}
_ONSITE_TYPES = {"0"}


def scrape(company: str, slug: str) -> list[Job]:
    try:
        r = httpx.get(
            LIST_URL.format(slug=slug),
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ScraperError(f"BambooHR request failed for {slug}: {e}") from e

    jobs = []
    for item in r.json().get("result", []):
        job_id = str(item["id"])
        loc = item.get("location", {})
        city = loc.get("city") or ""
        state = loc.get("state") or ""
        location = ", ".join(filter(None, [city, state])) or None
        loc_type = str(item.get("locationType", ""))
        remote = True if loc_type in _REMOTE_TYPES else (False if loc_type in _ONSITE_TYPES else None)

        jobs.append(Job(
            id=f"bamboo-{slug}-{job_id}",
            company=company,
            company_slug=slug,
            title=item["jobOpeningName"],
            url=f"https://{slug}.bamboohr.com/careers/{job_id}",
            source="bamboo",
            location=location,
            remote=remote,
            posted_at=None,
            raw_text="",
        ))

    return jobs
