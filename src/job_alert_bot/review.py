from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .filters import location_priority, match_score
from .models import APPLICATION_STATUSES, JobApplicationStatus, JobPosting

ACTIVE_PIPELINE_STATUSES = ("applied", "interview", "in progress", "offer")
REVIEWABLE_STATUSES = ("saved",)
STATUS_ALIAS_MAP = {
    "saved": "saved",
    "applied": "applied",
    "interview": "interview",
    "in-progress": "in progress",
    "rejected": "rejected",
    "offer": "offer",
    "closed": "closed",
}


@dataclass(frozen=True)
class ReviewQueueItem:
    job: JobPosting
    status: str | None
    score: int
    age_minutes: int | None
    reason: str | None = None
    needs_link_review: bool = False


def normalize_status_alias(value: str) -> str:
    normalized = STATUS_ALIAS_MAP.get(value, value)
    if normalized not in APPLICATION_STATUSES:
        raise ValueError(f"Unknown application status: {value}")
    return normalized


def build_review_queue(
    jobs: list[JobPosting],
    statuses: dict[str, JobApplicationStatus],
    include_keywords: list[str],
    preferred_locations: list[str],
    minimum_age_minutes: int = 60,
) -> list[ReviewQueueItem]:
    threshold = datetime.now(UTC) - timedelta(minutes=minimum_age_minutes)
    items: list[ReviewQueueItem] = []

    for job in jobs:
        status_record = statuses.get(job.dedupe_key)
        current_status = status_record.status if status_record is not None else None
        if current_status not in {None, *REVIEWABLE_STATUSES}:
            continue

        reference_time = job.posted_at or job.first_seen_at
        if reference_time is None or reference_time > threshold:
            continue

        score = job.rank_score if job.rank_score is not None else match_score(job, include_keywords, preferred_locations)
        age_minutes = int((datetime.now(UTC) - reference_time).total_seconds() // 60)
        items.append(
            ReviewQueueItem(
                job=job,
                status=current_status,
                score=score,
                age_minutes=age_minutes,
                reason=job.rank_reason,
                needs_link_review=(job.link_confidence or "").lower() in {"", "low"},
            )
        )

    items.sort(
        key=lambda item: (
            -item.score,
            location_priority(item.job, preferred_locations),
            -(item.age_minutes or 0),
            item.job.company.lower(),
            item.job.title.lower(),
        )
    )
    return items


def group_status_board(records: list[JobApplicationStatus]) -> dict[str, list[JobApplicationStatus]]:
    grouped: dict[str, list[JobApplicationStatus]] = {status: [] for status in APPLICATION_STATUSES}
    for record in records:
        grouped.setdefault(record.status, []).append(record)

    for status, items in grouped.items():
        items.sort(
            key=lambda item: (
                item.company or "",
                item.title or "",
                -item.updated_at.timestamp(),
            )
        )
    return grouped
