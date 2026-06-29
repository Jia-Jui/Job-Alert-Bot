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
    first_seen_at: datetime | None = None
    public_job_url: str | None = None
    resolved_apply_url: str | None = None
    referral_or_tracking_url: str | None = None
    link_source: str | None = None
    link_confidence: str | None = None
    link_resolution_notes: str | None = None
    rank_score: int | None = None
    rank_reason: str | None = None
    exclusion_flags: str | None = None
    seniority_hint: str | None = None
    work_mode: str | None = None
    company_priority: int | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.source}:{self.external_id}"

    @property
    def best_apply_url(self) -> str:
        for value in (self.referral_or_tracking_url, self.resolved_apply_url, self.public_job_url, self.link):
            if value:
                return value
        return ""

    @property
    def original_job_url(self) -> str:
        return self.public_job_url or self.link


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
    public_job_url: str | None = None
    resolved_apply_url: str | None = None
    referral_or_tracking_url: str | None = None
    link_confidence: str | None = None
    rank_score: int | None = None
    rank_reason: str | None = None

    @property
    def best_apply_url(self) -> str:
        for value in (self.referral_or_tracking_url, self.resolved_apply_url, self.public_job_url, self.link):
            if value:
                return value
        return ""
