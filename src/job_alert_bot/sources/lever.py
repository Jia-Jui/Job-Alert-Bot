from __future__ import annotations

from datetime import UTC, datetime

from ..models import JobPosting
from .base import SourceClient


def fetch_lever_jobs(client: SourceClient, company: str, slug: str) -> list[JobPosting]:
    url = f"https://jobs.lever.co/{slug}?mode=json"
    payload = client.get_json(url)
    jobs: list[JobPosting] = []

    for item in payload:
        categories = item.get("categories") or {}
        location = categories.get("location", "Unknown")
        jobs.append(
            JobPosting(
                source="lever",
                external_id=str(item.get("id") or item.get("hostedUrl")),
                company=company,
                title=item.get("text", "").strip(),
                location=location,
                link=item.get("hostedUrl", "").strip(),
                posted_at=_parse_lever_posted_at(item.get("createdAt")),
            )
        )

    return jobs


def _parse_lever_posted_at(value) -> datetime | None:
    if value in (None, ""):
        return None

    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None

    if timestamp > 10_000_000_000:
        timestamp /= 1000

    try:
        return datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError):
        return None
