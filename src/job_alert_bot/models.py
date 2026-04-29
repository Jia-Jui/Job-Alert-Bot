from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class JobPosting:
    source: str
    external_id: str
    company: str
    title: str
    location: str
    link: str
    posted_at: datetime | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.source}:{self.external_id}"
