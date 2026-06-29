from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.models import JobPosting
from job_alert_bot.notifiers.common import job_summary_lines


class NotificationTests(unittest.TestCase):
    def test_job_summary_uses_best_apply_link_and_reason(self) -> None:
        job = JobPosting(
            source="greenhouse",
            external_id="1",
            company="Acme",
            title="Backend Engineer",
            location="Phoenix, AZ",
            link="https://boards.example.com/jobs/1",
            public_job_url="https://boards.example.com/jobs/1",
            resolved_apply_url="https://apply.example.com/jobs/1",
            referral_or_tracking_url="https://apply.example.com/jobs/1?ref=friend",
            link_confidence="high",
            link_source="html",
            rank_score=11,
            rank_reason="Strong title match, preferred location, fresh posting, direct apply link found.",
        )

        lines = job_summary_lines(job)

        self.assertIn("Best apply link: https://apply.example.com/jobs/1?ref=friend", lines)
        self.assertIn("Original job link: https://boards.example.com/jobs/1", lines)
        self.assertIn("Score: 11", lines)
        self.assertIn("Link confidence: high", lines)
        self.assertIn("Why: Strong title match, preferred location, fresh posting, direct apply link found.", lines)


if __name__ == "__main__":
    unittest.main()
