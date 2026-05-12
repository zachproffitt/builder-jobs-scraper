from dataclasses import dataclass
from datetime import datetime


@dataclass
class Job:
    id: str
    company: str
    company_slug: str
    title: str
    url: str
    source: str          # "greenhouse", "lever", "ashby"
    location: str | None = None
    remote: bool | None = None
    posted_at: datetime | None = None
    raw_text: str = ""


class ScraperError(Exception):
    pass
