from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    id: str
    company: str
    company_slug: str
    title: str
    url: str
    source: str  # "greenhouse", "lever", "ashby", etc.
    location: Optional[str] = None
    remote: Optional[bool] = None
    posted_at: Optional[datetime] = None
    raw_text: str = ""
    departments: list[str] = field(default_factory=list)


class ScraperError(Exception):
    pass
