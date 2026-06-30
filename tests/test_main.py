from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.config import AppConfig
from job_alert_bot.main import MAX_POTENTIAL_LINK_BONUS, _should_skip_before_resolution, main
from job_alert_bot.models import JobPosting


class _FakeStore:
    def __init__(self, seen_keys: set[str] | None = None) -> None:
        self.seen_keys = seen_keys or set()
        self.saved_jobs: list[JobPosting] = []

    def is_seen(self, job: JobPosting) -> bool:
        return job.dedupe_key in self.seen_keys

    def save_job(self, job: JobPosting) -> None:
        self.saved_jobs.append(job)


class _DummyClient:
    def __init__(self, timeout_seconds: int, request_delay_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds


class MainFlowTests(unittest.TestCase):
    def test_main_skips_resolution_for_seen_duplicates_and_clear_mismatches(self) -> None:
        store = _FakeStore(seen_keys={"lever:seen-1"})
        config = AppConfig(
            notification_channel="telegram",
            include_keywords=["backend", "python", "software engineer"],
            exclude_keywords=["senior"],
            preferred_locations=["phoenix", "remote"],
            min_match_score=4,
        )
        jobs = [
            JobPosting(
                source="lever",
                external_id="seen-1",
                company="Seen Co",
                title="Backend Engineer",
                location="Remote",
                link="https://example.com/jobs/seen-1",
            ),
            JobPosting(
                source="lever",
                external_id="weak-1",
                company="Weak Co",
                title="Marketing Associate",
                location="Phoenix, AZ",
                link="https://example.com/jobs/weak-1",
            ),
            JobPosting(
                source="lever",
                external_id="keep-1",
                company="Keep Co",
                title="Backend Engineer",
                location="Phoenix, AZ",
                link="https://example.com/jobs/shared",
            ),
            JobPosting(
                source="lever",
                external_id="dup-1",
                company="Dup Co",
                title="Backend Engineer",
                location="Phoenix, AZ",
                link="https://example.com/jobs/shared",
            ),
        ]
        resolve_calls: list[str] = []

        def fake_resolve(job: JobPosting, _client, _config: AppConfig) -> JobPosting:
            resolve_calls.append(job.dedupe_key)
            return JobPosting(
                source=job.source,
                external_id=job.external_id,
                company=job.company,
                title=job.title,
                location=job.location,
                link=job.link,
                public_job_url=job.link,
                resolved_apply_url=f"{job.link}/apply",
                link_source="html",
                link_confidence="high",
            )

        with (
            patch("job_alert_bot.main.load_config", return_value=(config, {"lever": [], "greenhouse": [], "github_raw_readmes": []})),
            patch("job_alert_bot.main.validate_notification_config"),
            patch("job_alert_bot.main.build_seen_jobs_store", return_value=store),
            patch("job_alert_bot.main.SourceClient", _DummyClient),
            patch("job_alert_bot.main._collect_jobs", return_value=jobs),
            patch("job_alert_bot.main.resolve_job_links", side_effect=fake_resolve),
            patch("job_alert_bot.main._send_notification"),
            patch("job_alert_bot.main._send_digest_notification"),
        ):
            result = main()

        self.assertEqual(result, 0)
        self.assertEqual(resolve_calls, ["lever:keep-1"])
        self.assertEqual([job.dedupe_key for job in store.saved_jobs], ["lever:keep-1"])

    def test_skip_helper_keeps_near_threshold_jobs_for_resolution(self) -> None:
        job = JobPosting(
            source="lever",
            external_id="near-1",
            company="Near Co",
            title="Software Engineer",
            location="Remote",
            link="https://example.com/jobs/near-1",
            rank_score=4 - MAX_POTENTIAL_LINK_BONUS,
        )
        self.assertFalse(_should_skip_before_resolution(job, 4))


if __name__ == "__main__":
    unittest.main()
