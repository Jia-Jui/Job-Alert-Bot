from __future__ import annotations

from datetime import UTC, datetime

from ..models import JobPosting
from .base import SourceClient


def fetch_greenhouse_jobs(client: SourceClient, company: str, board_token: str) -> list[JobPosting]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    payload = client.get_json(url)
    jobs: list[JobPosting] = []

    for item in payload.get("jobs", []):
        location = (item.get("location") or {}).get("name", "Unknown")
        jobs.append(
            JobPosting(
                source="greenhouse",
                external_id=str(item.get("id") or item.get("absolute_url")),
                company=company,
                title=item.get("title", "").strip(),
                location=location,
                link=item.get("absolute_url", "").strip(),
                posted_at=_parse_greenhouse_posted_at(item),
            )
        )

    return jobs


def _parse_greenhouse_posted_at(item: dict) -> datetime | None:
    for key in ("updated_at", "created_at", "updatedAt", "createdAt"):
        value = item.get(key)
        parsed = _parse_iso_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
