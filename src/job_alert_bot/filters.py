from __future__ import annotations

from .models import JobPosting


def matches_keywords(job: JobPosting, include_keywords: list[str], exclude_keywords: list[str]) -> bool:
    haystack = " ".join([job.title, job.company, job.location]).lower()

    if any(keyword.lower() in haystack for keyword in exclude_keywords):
        return False

    title_text = job.title.lower()
    return any(keyword.lower() in title_text for keyword in include_keywords)


def location_priority(job: JobPosting, preferred_locations: list[str]) -> tuple[int, int, str, str]:
    location_text = job.location.lower()
    title_text = job.title.lower()

    for index, preferred in enumerate(preferred_locations):
        if preferred in location_text:
            return (0, index, location_text, title_text)

    return (1, len(preferred_locations), location_text, title_text)


def match_score(job: JobPosting, include_keywords: list[str], preferred_locations: list[str]) -> int:
    title_text = job.title.lower()
    score = 0

    for keyword in include_keywords:
        normalized = keyword.lower()
        if normalized in title_text:
            if normalized in {"backend", "python", "aws", "api", "serverless", "rest"}:
                score += 4
            elif normalized in {"full stack", "fullstack"}:
                score += 3
            elif normalized in {"software engineer", "software development engineer"}:
                score += 2
            elif normalized in {"associate", "entry level", "new grad", "junior", "early career", "software engineer i", "sde i"}:
                score += 3
            else:
                score += 2

    location_rank = location_priority(job, preferred_locations)
    if location_rank[0] == 0:
        score += max(1, 4 - min(location_rank[1], 3))

    return score
