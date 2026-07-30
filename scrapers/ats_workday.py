import re
from datetime import date

import httpx

from ._base import Job, ScraperError, html_to_text

API_URL = "https://{tenant}.{partition}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"
JOB_URL = "https://{tenant}.{partition}.myworkdayjobs.com/{board}{path}"

# Requisition IDs sit alongside the location in bulletFields — "R00333571",
# "12345", "JR-2024-8871". Anything of that shape is not a place name.
_REQ_ID_RE = re.compile(r"^[A-Z]{0,4}[-_]?\d[\w-]*$", re.IGNORECASE)


def _location_from(item: dict) -> str | None:
    """Workday tenants disagree about where the location lives.

    Most return `locationsText`. Some (Accenture, for one) omit it entirely and
    put the location in `bulletFields` next to the requisition ID:
    `['R00333571', 'Riga']`. Without this fallback those postings arrive with no
    location at all, which defeats the pre-LLM geographic filter and sends every
    one of them to the classifier.
    """
    text = item.get("locationsText")
    if text and text.strip():
        return text.strip()

    bullets = [str(b).strip() for b in (item.get("bulletFields") or []) if str(b).strip()]
    places = [b for b in bullets if not _REQ_ID_RE.match(b)]
    return " / ".join(places) if places else None


def scrape(company: str, slug: str) -> list[Job]:
    # slug format: tenant/partition/board (e.g. crowdstrike/wd5/crowdstrikecareers)
    try:
        tenant, partition, board = slug.split("/", 2)
    except ValueError:
        raise ScraperError(f"Workday slug must be tenant/partition/board, got: {slug!r}")

    url = API_URL.format(tenant=tenant, partition=partition, board=board)
    offset = 0
    limit = 20
    total = None  # only populated on first response
    all_postings = []

    try:
        while True:
            r = httpx.post(
                url,
                json={"limit": limit, "offset": offset, "searchText": "", "appliedFacets": {}},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            postings = data.get("jobPostings", [])
            if not postings:
                break
            all_postings.extend(postings)
            if total is None:
                total = data.get("total", 0)
            if len(all_postings) >= total:
                break
            offset += limit
    except httpx.HTTPError as e:
        raise ScraperError(f"Workday request failed for {slug}: {e}") from e
    except Exception as e:
        raise ScraperError(f"Workday unexpected error for {slug}: {e}") from e

    jobs = []
    for item in all_postings:
        external_path = item.get("externalPath", "")
        job_url = JOB_URL.format(tenant=tenant, partition=partition, board=board, path=external_path)
        # Extract a native ID from the path (last path segment)
        native_id = external_path.rsplit("/", 1)[-1] if "/" in external_path else external_path

        location = _location_from(item)
        remote = "remote" in (location or "").lower()

        jobs.append(Job(
            id=f"workday-{tenant}-{native_id}",
            company=company,
            company_slug=slug,
            title=item.get("title") or item.get("jobTitle", ""),
            url=job_url,
            source="workday",
            location=location,
            remote=remote,
            posted_at=None,
            raw_text="",
        ))

    return jobs
