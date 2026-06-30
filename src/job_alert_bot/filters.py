from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import JobPosting

STRONG_STACK_KEYWORDS = {"backend", "python", "aws", "api", "serverless", "rest"}
GENERAL_ENGINEERING_KEYWORDS = {"software engineer", "software development engineer"}
ENTRY_LEVEL_HINTS = {
    "associate",
    "entry level",
    "new grad",
    "junior",
    "early career",
    "software engineer i",
    "sde i",
}
SENIORITY_EXCLUSION_HINTS = {"senior", "staff", "principal", "lead"}
HYBRID_HINTS = ("hybrid",)
REMOTE_HINTS = ("remote", "work from home", "distributed")
ONSITE_HINTS = ("onsite", "on-site", "in office", "in-office")
US_REMOTE_HINTS = (
    "united states",
    "u.s.",
    "u.s.a.",
    "usa",
    "us-only",
    "us only",
    "u.s.-only",
    "remote us",
    "remote - us",
    "remote, us",
)
NON_US_REMOTE_HINTS = (
    "canada",
    "emea",
    "europe",
    "eu only",
    "eu-only",
    "uk",
    "united kingdom",
    "india",
    "apac",
    "australia",
    "new zealand",
    "latam",
    "latin america",
    "mexico",
    "singapore",
)


@dataclass(frozen=True)
class RankingResult:
    score: int
    reason: str
    exclusion_flags: tuple[str, ...]
    title_match: bool
    seniority_hint: str
    work_mode: str

    @property
    def is_excluded(self) -> bool:
        return bool(self.exclusion_flags)


def matches_keywords(job: JobPosting, include_keywords: list[str], exclude_keywords: list[str]) -> bool:
    result = evaluate_job(
        job,
        include_keywords=include_keywords,
        exclude_keywords=exclude_keywords,
        preferred_locations=[],
        company_priorities={},
        fresh_window_minutes=60,
    )
    return result.title_match and not result.is_excluded


def location_priority(job: JobPosting, preferred_locations: list[str]) -> tuple[int, int, str, str]:
    location_text = job.location.lower()
    title_text = job.title.lower()

    for index, preferred in enumerate(preferred_locations):
        if preferred == "remote" and not _is_us_remote_location(location_text):
            continue
        if preferred in location_text:
            return (0, index, location_text, title_text)

    return (1, len(preferred_locations), location_text, title_text)


def match_score(job: JobPosting, include_keywords: list[str], preferred_locations: list[str]) -> int:
    result = evaluate_job(
        job,
        include_keywords=include_keywords,
        exclude_keywords=[],
        preferred_locations=preferred_locations,
        company_priorities={},
        fresh_window_minutes=60,
    )
    return result.score


def evaluate_job(
    job: JobPosting,
    include_keywords: list[str],
    exclude_keywords: list[str],
    preferred_locations: list[str],
    company_priorities: dict[str, int],
    fresh_window_minutes: int,
) -> RankingResult:
    title_text = job.title.lower()
    location_text = job.location.lower()
    company_text = job.company.lower()
    haystack = " ".join([job.title, job.company, job.location]).lower()
    score = 0
    reasons: list[str] = []
    exclusion_flags: list[str] = []

    seniority_hint = _detect_seniority(title_text)
    work_mode = _detect_work_mode(location_text)

    for keyword in exclude_keywords:
        normalized = keyword.lower()
        if normalized in haystack:
            exclusion_flags.append(f"keyword:{normalized}")

    if seniority_hint in {"senior", "staff", "principal", "lead"}:
        exclusion_flags.append(f"seniority:{seniority_hint}")
    if work_mode == "remote" and not _is_us_remote_location(location_text):
        exclusion_flags.append("remote_outside_us")

    title_match = False
    for keyword in include_keywords:
        normalized = keyword.lower()
        if normalized not in title_text:
            continue
        title_match = True
        if normalized in STRONG_STACK_KEYWORDS:
            score += 4
        elif normalized in {"full stack", "fullstack"}:
            score += 3
        elif normalized in GENERAL_ENGINEERING_KEYWORDS:
            score += 2
        elif normalized in ENTRY_LEVEL_HINTS:
            score += 3
        else:
            score += 2

    if title_match:
        reasons.append("Strong title match" if score >= 4 else "Relevant title match")
    else:
        exclusion_flags.append("no_title_match")

    if seniority_hint in {"entry", "junior"}:
        score += 3
        reasons.append("Entry-level seniority")
    elif seniority_hint == "mid":
        score += 1

    location_rank = location_priority(job, preferred_locations)
    if location_rank[0] == 0:
        location_bonus = max(1, 4 - min(location_rank[1], 3))
        score += location_bonus
        reasons.append("Preferred location")
    elif work_mode == "remote":
        score += 2
        reasons.append("Remote-friendly (U.S.)")
    elif work_mode == "hybrid":
        score += 1
        reasons.append("Hybrid option")

    if job.posted_at and job.posted_at >= datetime.now(UTC) - timedelta(minutes=fresh_window_minutes):
        score += 2
        reasons.append("Fresh posting")

    company_priority = company_priorities.get(company_text, 0)
    if company_priority:
        score += company_priority
        reasons.append("Priority company")

    confidence_bonus = {"high": 2, "medium": 1}.get((job.link_confidence or "").lower(), 0)
    if confidence_bonus:
        score += confidence_bonus
        reasons.append("Direct apply link found" if confidence_bonus == 2 else "Apply link likely available")

    if job.referral_or_tracking_url:
        score += 1
        reasons.append("Referral or tracked link available")

    reason = ", ".join(dict.fromkeys(reasons)) if reasons else "Limited match signal."
    return RankingResult(
        score=score,
        reason=reason,
        exclusion_flags=tuple(dict.fromkeys(exclusion_flags)),
        title_match=title_match,
        seniority_hint=seniority_hint,
        work_mode=work_mode,
    )


def _detect_seniority(title_text: str) -> str:
    if any(hint in title_text for hint in SENIORITY_EXCLUSION_HINTS):
        for hint in ("principal", "staff", "senior", "lead"):
            if hint in title_text:
                return hint
    if any(hint in title_text for hint in ENTRY_LEVEL_HINTS):
        return "entry" if any(hint in title_text for hint in {"entry level", "new grad", "associate", "early career"}) else "junior"
    if any(hint in title_text for hint in ("ii", "2", "mid")):
        return "mid"
    return "unknown"


def _detect_work_mode(location_text: str) -> str:
    if any(hint in location_text for hint in REMOTE_HINTS):
        return "remote"
    if any(hint in location_text for hint in HYBRID_HINTS):
        return "hybrid"
    if any(hint in location_text for hint in ONSITE_HINTS):
        return "onsite"
    return "unknown"


def _is_us_remote_location(location_text: str) -> bool:
    if not any(hint in location_text for hint in REMOTE_HINTS):
        return False
    if any(hint in location_text for hint in NON_US_REMOTE_HINTS):
        return False
    if any(hint in location_text for hint in US_REMOTE_HINTS):
        return True
    return _mentions_us_state(location_text)


def _mentions_us_state(location_text: str) -> bool:
    return any(
        hint in location_text
        for hint in (
            "arizona",
            "az",
            "california",
            "ca",
            "washington",
            "wa",
            "texas",
            "tx",
            "phoenix",
            "scottsdale",
            "tempe",
            "mesa",
            "seattle",
        )
    )
