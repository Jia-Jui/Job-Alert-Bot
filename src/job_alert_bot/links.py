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
        if any(hint in combined for hint in APPLY_TEXT_HINTS):
            return urljoin(url, href), "Parsed a likely apply link from the public job detail page."
    return None, "No explicit apply anchor was found on the public page."


def _advanced_public_link_discovery(client: SourceClient, url: str, config: AppConfig) -> tuple[str | None, str, str | None]:
    try:
        html = client.get_text(url, timeout_seconds=config.link_discovery_timeout_seconds)
    except Exception:
        return None, "low", "Advanced public discovery could not load the page."

    pages_checked = 1
    best_candidate: str | None = None

    parser = _AnchorParser()
    parser.feed(html)
    for href, _combined in parser.links:
        if pages_checked >= config.link_discovery_max_pages:
            break
        href = urljoin(url, href)
        if not href.startswith("http"):
            continue
        if any(hint in href.lower() for hint in TRACKING_HINTS):
            best_candidate = href
            break
        if not _same_host(href, url):
            continue
        pages_checked += 1
        nested_candidate, _ = _extract_apply_link_from_page(client, href, config.link_discovery_timeout_seconds)
        if nested_candidate:
            best_candidate = nested_candidate
            break

    if best_candidate:
        return best_candidate, "medium", "Advanced public discovery found a candidate by following additional public page links."
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


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        href = attr_map.get("href", "").strip()
        if not href:
            return
        self._current_href = href
        self._current_parts = [attr_map.get("aria-label", "").strip().lower(), attr_map.get("class", "").strip().lower()]

    def handle_data(self, data: str) -> None:
        if self._current_href is None:
            return
        self._current_parts.append(data.strip().lower())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        combined = " ".join(part for part in self._current_parts if part).strip()
        self.links.append((self._current_href, combined))
        self._current_href = None
        self._current_parts = []
