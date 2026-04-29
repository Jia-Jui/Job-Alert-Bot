from __future__ import annotations

import re

from ..models import JobPosting
from .base import SourceClient


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def fetch_jobs_from_readme(client: SourceClient, raw_readme_url: str) -> list[JobPosting]:
    text = client.get_text(raw_readme_url)
    repo_name = _repo_name_from_raw_url(raw_readme_url)
    jobs: list[JobPosting] = []

    for line in text.splitlines():
        if "|" not in line or "http" not in line:
            continue

        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue

        company = _clean_markdown(parts[0])
        title = _clean_markdown(parts[1])
        location = _clean_markdown(parts[2])
        link = _extract_first_url(line)
        if not company or not title or not link:
            continue

        external_id = link
        jobs.append(
            JobPosting(
                source=f"github:{repo_name}",
                external_id=external_id,
                company=company,
                title=title,
                location=location or "Unknown",
                link=link,
            )
        )

    return jobs


def _extract_first_url(text: str) -> str:
    match = MARKDOWN_LINK_RE.search(text)
    return match.group(2).strip() if match else ""


def _clean_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _repo_name_from_raw_url(raw_url: str) -> str:
    match = re.search(r"raw\.githubusercontent\.com/([^/]+/[^/]+)/", raw_url)
    return match.group(1) if match else "repo"
