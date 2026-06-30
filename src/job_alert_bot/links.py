from __future__ import annotations

from dataclasses import replace
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .config import AppConfig
from .models import JobPosting
from .sources.base import SourceClient

LINK_CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}
APPLY_TEXT_HINTS = (
    "apply",
    "application",
    "submit application",
    "refer",
    "referral",
    "candidate portal",
)
FOLLOW_UP_LINK_LIMIT = 12
TRACKING_HINTS = (
    "referral",
    "gh_jid",
    "lever-via",
    "ashby",
    "greenhouse",
    "workday",
    "myworkdayjobs",
)


def resolve_job_links(job: JobPosting, client: SourceClient, config: AppConfig) -> JobPosting:
    public_job_url = job.public_job_url or job.link
    if not public_job_url:
        return replace(
            job,
            public_job_url=job.link,
            resolved_apply_url=job.link,
            link_source="original",
            link_confidence="low",
            link_resolution_notes="No public job URL was available; kept the original link.",
        )

    best_link = public_job_url
    best_confidence = "high"
    link_source = "official_api"
    notes = ["Started from the source-provided public job URL."]
    referral_or_tracking_url = _tracking_link(public_job_url)

    redirect_target = _resolve_redirect_target(client, public_job_url, config.link_discovery_timeout_seconds)
    if redirect_target and redirect_target != public_job_url:
        best_link = redirect_target
        link_source = "redirect"
        best_confidence = "high"
        notes.append("Followed the public HTTP redirect target.")
        referral_or_tracking_url = _tracking_link(redirect_target) or referral_or_tracking_url

    html_candidate, html_note = _extract_apply_link_from_page(
        client,
        redirect_target or public_job_url,
        config.link_discovery_timeout_seconds,
    )
    if html_note:
        notes.append(html_note)
    if html_candidate:
        best_link = html_candidate
        link_source = "html"
        best_confidence = "high" if _same_host(html_candidate, public_job_url) else "medium"
        referral_or_tracking_url = _tracking_link(html_candidate) or referral_or_tracking_url

    if config.enable_advanced_link_discovery:
        advanced_link, advanced_confidence, advanced_note = _advanced_public_link_discovery(
            client,
            redirect_target or public_job_url,
            config,
        )
        if advanced_note:
            notes.append(advanced_note)
        if advanced_link and _is_better_link(best_link, html_candidate is not None, advanced_confidence):
            best_link = advanced_link
            best_confidence = advanced_confidence
            link_source = "advanced_public_discovery"
            referral_or_tracking_url = _tracking_link(advanced_link) or referral_or_tracking_url

    if not best_link:
        best_link = public_job_url
        best_confidence = "low"
        link_source = "fallback"
        notes.append("Fell back to the original public job URL.")

    return replace(
        job,
        public_job_url=public_job_url,
        resolved_apply_url=best_link,
        referral_or_tracking_url=referral_or_tracking_url,
        link_source=link_source,
        link_confidence=best_confidence,
        link_resolution_notes=" ".join(dict.fromkeys(notes)),
    )


def choose_notification_apply_url(job: JobPosting) -> str:
    return job.best_apply_url or job.link


def _resolve_redirect_target(client: SourceClient, url: str, timeout_seconds: int) -> str | None:
    try:
        response = client.get_response(url, timeout_seconds=timeout_seconds, allow_redirects=True)
    except Exception:
        return None
    return response.url.strip() if response.url else None


def _extract_apply_link_from_page(client: SourceClient, url: str, timeout_seconds: int) -> tuple[str | None, str | None]:
    try:
        html = client.get_text(url, timeout_seconds=timeout_seconds)
    except Exception:
        return None, None

    parser = _AnchorParser()
    parser.feed(html)
    for href, combined in parser.links:
        if _looks_like_apply_target(href, combined):
            return urljoin(url, href), "Parsed a likely apply link from the public job detail page."
    return None, "No explicit apply anchor was found on the public page."


def _advanced_public_link_discovery(client: SourceClient, url: str, config: AppConfig) -> tuple[str | None, str, str | None]:
    frontier = [url]
    visited: set[str] = set()
    best_tracking: str | None = None
    pages_checked = 0

    while frontier and pages_checked < config.link_discovery_max_pages:
        current = frontier.pop(0)
        if current in visited:
            continue
        visited.add(current)
        pages_checked += 1

        try:
            html = client.get_text(current, timeout_seconds=config.link_discovery_timeout_seconds)
        except Exception:
            continue

        parser = _AnchorParser()
        parser.feed(html)
        for href, combined in parser.links[:FOLLOW_UP_LINK_LIMIT]:
            absolute = urljoin(current, href)
            if not absolute.startswith("http"):
                continue

            if _looks_like_apply_target(absolute, combined):
                redirect_target = _resolve_redirect_target(client, absolute, config.link_discovery_timeout_seconds)
                candidate = redirect_target or absolute
                confidence = "high" if _same_host(candidate, current) else "medium"
                note = f"Advanced public discovery found a likely apply path after checking {pages_checked} public page(s)."
                return candidate, confidence, note

            if _tracking_link(absolute) and best_tracking is None:
                best_tracking = absolute

            if _same_host(absolute, current) and absolute not in visited and absolute not in frontier:
                frontier.append(absolute)

    if best_tracking:
        note = f"Advanced public discovery found a likely referral or tracking link after checking {pages_checked} public page(s)."
        return best_tracking, "medium", note
    return None, "low", "Advanced public discovery did not improve the apply link."


def _is_better_link(current_link: str | None, current_from_html: bool, candidate_confidence: str) -> bool:
    if not current_link:
        return True
    if not current_from_html:
        return True
    return LINK_CONFIDENCE_ORDER.get(candidate_confidence, 0) > LINK_CONFIDENCE_ORDER.get("medium", 0)


def _tracking_link(url: str | None) -> str | None:
    if not url:
        return None
    lowered = url.lower()
    if any(hint in lowered for hint in TRACKING_HINTS):
        return url
    return None


def _same_host(first: str, second: str) -> bool:
    return urlparse(first).netloc.lower() == urlparse(second).netloc.lower()


def _looks_like_apply_target(href: str, combined: str) -> bool:
    lowered_href = href.lower()
    lowered_combined = combined.lower()
    return any(hint in lowered_combined for hint in APPLY_TEXT_HINTS) or any(hint in lowered_href for hint in APPLY_TEXT_HINTS)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_parts: list[str] = []
        self._current_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        tag_name = tag.lower()
        href = ""
        if tag_name == "a":
            href = attr_map.get("href", "").strip()
        elif tag_name == "form":
            href = attr_map.get("action", "").strip()
        elif tag_name in {"button", "input"}:
            href = (
                attr_map.get("formaction", "").strip()
                or attr_map.get("data-apply-url", "").strip()
                or attr_map.get("data-url", "").strip()
            )
        if not href:
            return
        self._current_href = href
        self._current_tag = tag_name
        self._current_parts = [
            attr_map.get("aria-label", "").strip().lower(),
            attr_map.get("class", "").strip().lower(),
            attr_map.get("title", "").strip().lower(),
            attr_map.get("id", "").strip().lower(),
            attr_map.get("name", "").strip().lower(),
            attr_map.get("value", "").strip().lower(),
            attr_map.get("data-qa", "").strip().lower(),
            attr_map.get("data-testid", "").strip().lower(),
        ]
        if tag_name in {"form", "input"}:
            combined = " ".join(part for part in self._current_parts if part).strip()
            self.links.append((self._current_href, combined))
            self._current_href = None
            self._current_parts = []
            self._current_tag = None

    def handle_data(self, data: str) -> None:
        if self._current_href is None:
            return
        self._current_parts.append(data.strip().lower())

    def handle_endtag(self, tag: str) -> None:
        if self._current_href is None:
            return
        tag_name = tag.lower()
        if tag_name != self._current_tag:
            return
        combined = " ".join(part for part in self._current_parts if part).strip()
        self.links.append((self._current_href, combined))
        self._current_href = None
        self._current_parts = []
        self._current_tag = None
