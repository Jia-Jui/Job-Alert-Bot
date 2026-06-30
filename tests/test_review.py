from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.filters import evaluate_job, location_priority
from job_alert_bot.models import JobApplicationStatus, JobPosting
from job_alert_bot.review import ACTIVE_PIPELINE_STATUSES, build_review_queue, group_status_board, normalize_status_alias


class ReviewTests(unittest.TestCase):
    def test_review_queue_keeps_older_unapplied_jobs(self) -> None:
        older = datetime.now(UTC) - timedelta(hours=2)
        recent = datetime.now(UTC) - timedelta(minutes=20)
        jobs = [
            JobPosting(
                source="lever",
                external_id="old-1",
                company="Acme",
                title="Backend Engineer",
                location="Phoenix, AZ",
                link="https://example.com/old-1",
                posted_at=older,
            ),
            JobPosting(
                source="lever",
                external_id="recent-1",
                company="Beta",
                title="Backend Engineer",
                location="Remote",
                link="https://example.com/recent-1",
                posted_at=recent,
            ),
            JobPosting(
                source="lever",
                external_id="applied-1",
                company="Gamma",
                title="Backend Engineer",
                location="Remote",
                link="https://example.com/applied-1",
                posted_at=older,
            ),
        ]
        statuses = {
            "lever:applied-1": JobApplicationStatus(
                dedupe_key="lever:applied-1",
                status="applied",
                updated_at=older,
            )
        }

        queue = build_review_queue(
            jobs=jobs,
            statuses=statuses,
            include_keywords=["backend", "python", "software engineer"],
            preferred_locations=["phoenix", "remote"],
            minimum_age_minutes=60,
        )

        self.assertEqual([item.job.dedupe_key for item in queue], ["lever:old-1"])
        self.assertGreaterEqual(queue[0].score, 1)

    def test_status_aliases_and_board_grouping(self) -> None:
        self.assertEqual(normalize_status_alias("in-progress"), "in progress")
        self.assertIn("offer", ACTIVE_PIPELINE_STATUSES)

        records = [
            JobApplicationStatus(
                dedupe_key="lever:1",
                status="applied",
                updated_at=datetime(2026, 4, 29, 0, 0, tzinfo=UTC),
                company="Acme",
                title="Backend Engineer",
            ),
            JobApplicationStatus(
                dedupe_key="lever:2",
                status="rejected",
                updated_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
                company="Beta",
                title="Software Engineer I",
            ),
        ]

        grouped = group_status_board(records)

        self.assertEqual(len(grouped["applied"]), 1)
        self.assertEqual(len(grouped["rejected"]), 1)

    def test_remote_roles_must_be_us_based(self) -> None:
        us_remote = JobPosting(
            source="lever",
            external_id="us-1",
            company="Acme",
            title="Backend Engineer",
            location="Remote - United States",
            link="https://example.com/us-1",
        )
        canada_remote = JobPosting(
            source="lever",
            external_id="ca-1",
            company="Beta",
            title="Backend Engineer",
            location="Remote - Canada",
            link="https://example.com/ca-1",
        )

        us_result = evaluate_job(
            us_remote,
            include_keywords=["backend", "software engineer"],
            exclude_keywords=[],
            preferred_locations=["phoenix", "arizona", "remote", "california"],
            company_priorities={},
            fresh_window_minutes=60,
        )
        canada_result = evaluate_job(
            canada_remote,
            include_keywords=["backend", "software engineer"],
            exclude_keywords=[],
            preferred_locations=["phoenix", "arizona", "remote", "california"],
            company_priorities={},
            fresh_window_minutes=60,
        )

        self.assertNotIn("remote_outside_us", us_result.exclusion_flags)
        self.assertIn("Preferred location", us_result.reason)
        self.assertIn("remote_outside_us", canada_result.exclusion_flags)
        self.assertEqual(location_priority(us_remote, ["phoenix", "arizona", "remote", "california"])[0], 0)
        self.assertEqual(location_priority(canada_remote, ["phoenix", "arizona", "remote", "california"])[0], 1)


if __name__ == "__main__":
    unittest.main()
