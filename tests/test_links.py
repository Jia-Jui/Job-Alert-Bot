from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.config import AppConfig
from job_alert_bot.links import choose_notification_apply_url, resolve_job_links
from job_alert_bot.models import JobPosting


class _Response:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeClient:
    def __init__(self, redirect_map: dict[str, str] | None = None, html_map: dict[str, str] | None = None) -> None:
        self.redirect_map = redirect_map or {}
        self.html_map = html_map or {}

    def get_response(self, url: str, timeout_seconds: int | None = None, allow_redirects: bool = True) -> _Response:
        return _Response(self.redirect_map.get(url, url))

    def get_text(self, url: str, timeout_seconds: int | None = None) -> str:
        if url not in self.html_map:
            raise RuntimeError(f"No HTML stub for {url}")
        return self.html_map[url]


class LinkResolverTests(unittest.TestCase):
    def test_link_resolver_falls_back_to_original_url(self) -> None:
        job = JobPosting(
            source="github:test",
            external_id="1",
            company="Acme",
            title="Backend Engineer",
            location="Remote",
            link="https://example.com/jobs/1",
        )
        config = AppConfig(enable_advanced_link_discovery=False)
        resolved = resolve_job_links(job, _FakeClient(), config)

        self.assertEqual(resolved.public_job_url, "https://example.com/jobs/1")
        self.assertEqual(resolved.resolved_apply_url, "https://example.com/jobs/1")
        self.assertEqual(resolved.link_source, "official_api")
        self.assertEqual(choose_notification_apply_url(resolved), "https://example.com/jobs/1")

    def test_link_resolver_uses_redirect_target(self) -> None:
        job = JobPosting(
            source="greenhouse",
            external_id="2",
            company="Beta",
            title="Software Engineer",
            location="Phoenix",
            link="https://boards.example.com/jobs/2",
            public_job_url="https://boards.example.com/jobs/2",
        )
        config = AppConfig(enable_advanced_link_discovery=False)
        resolved = resolve_job_links(
            job,
            _FakeClient(redirect_map={"https://boards.example.com/jobs/2": "https://apply.example.com/2"}),
            config,
        )

        self.assertEqual(resolved.resolved_apply_url, "https://apply.example.com/2")
        self.assertEqual(resolved.link_source, "redirect")
        self.assertEqual(resolved.link_confidence, "high")

    def test_link_resolver_extracts_apply_anchor_from_html(self) -> None:
        job = JobPosting(
            source="lever",
            external_id="3",
            company="Gamma",
            title="Backend Python Engineer",
            location="Remote",
            link="https://jobs.example.com/3",
            public_job_url="https://jobs.example.com/3",
        )
        html = """
        <html>
          <body>
            <a href="/apply/3">Apply now</a>
          </body>
        </html>
        """
        config = AppConfig(enable_advanced_link_discovery=False)
        resolved = resolve_job_links(job, _FakeClient(html_map={"https://jobs.example.com/3": html}), config)

        self.assertEqual(resolved.resolved_apply_url, "https://jobs.example.com/apply/3")
        self.assertEqual(resolved.link_source, "html")
        self.assertEqual(resolved.link_confidence, "high")

    def test_notification_link_prefers_referral_then_resolved(self) -> None:
        job = JobPosting(
            source="greenhouse",
            external_id="4",
            company="Delta",
            title="API Engineer",
            location="Remote",
            link="https://jobs.example.com/4",
            public_job_url="https://jobs.example.com/4",
            resolved_apply_url="https://apply.example.com/4",
            referral_or_tracking_url="https://apply.example.com/4?ref=friend",
        )
        self.assertEqual(choose_notification_apply_url(job), "https://apply.example.com/4?ref=friend")


if __name__ == "__main__":
    unittest.main()
