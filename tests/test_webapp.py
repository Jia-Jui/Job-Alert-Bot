from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.config import load_app_config
from job_alert_bot.models import JobApplicationStatus, JobPosting
from job_alert_bot.webapp import _build_dashboard, _render_dashboard


class _SeenStore:
    def __init__(self, jobs: list[JobPosting]) -> None:
        self.jobs = jobs

    def list_seen_jobs(self) -> list[JobPosting]:
        return self.jobs


class _StatusStore:
    def __init__(self, records: list[JobApplicationStatus]) -> None:
        self.records = records

    def list_statuses(self, status: str | None = None) -> list[JobApplicationStatus]:
        if status is None:
            return self.records
        return [record for record in self.records if record.status == status]


class WebAppTests(unittest.TestCase):
    def test_dashboard_render_includes_queue_and_board_content(self) -> None:
        older = datetime.now(UTC) - timedelta(hours=3)
        jobs = [
            JobPosting(
                source="lever",
                external_id="job-1",
                company="Acme",
                title="Backend Engineer",
                location="Phoenix, AZ",
                link="https://example.com/job-1",
                posted_at=older,
            )
        ]
        statuses = [
            JobApplicationStatus(
                dedupe_key="lever:job-2",
                status="applied",
                updated_at=older,
                company="Beta",
                title="Software Engineer I",
                location="Remote",
                link="https://example.com/job-2",
            )
        ]
        dashboard = _build_dashboard(load_app_config(), _SeenStore(jobs), _StatusStore(statuses), 60, 40, 60)

        html = _render_dashboard(dashboard, "Saved")

        self.assertIn("Review Queue", html)
        self.assertIn("Active Pipeline", html)
        self.assertIn("Status Board", html)
        self.assertIn("Acme", html)
        self.assertIn("lever:job-1", html)
        self.assertIn("Data source", html)
        self.assertIn("job-search", html)

    def test_default_sqlite_path_points_to_repo_jobs_db(self) -> None:
        config = load_app_config()
        self.assertTrue(str(config.sqlite_db_path).endswith("jobs.db"))
        self.assertTrue(config.sqlite_db_path.is_absolute())


if __name__ == "__main__":
    unittest.main()
