from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

APPLICATION_STATUSES = (
    "saved",
    "applied",
    "interview",
    "in progress",
    "rejected",
    "offer",
    "closed",
)


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


@dataclass(frozen=True)
class JobApplicationStatus:
    dedupe_key: str
    status: str
    updated_at: datetime
    source: str | None = None
    external_id: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    link: str | None = None
