from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.db import FirebaseSeenJobsStore, SQLiteJobStatusStore, SQLiteSeenJobsStore
from job_alert_bot.models import JobPosting


class _FakeFirebaseChild:
    def __init__(self, recorder: dict) -> None:
        self.recorder = recorder

    def set(self, payload: dict) -> None:
        self.recorder["payload"] = payload


class _FakeFirebaseRoot:
    def __init__(self, recorder: dict) -> None:
        self.recorder = recorder

    def child(self, key: str) -> _FakeFirebaseChild:
        self.recorder["key"] = key
        return _FakeFirebaseChild(self.recorder)


class DbTests(unittest.TestCase):
    def test_firebase_seen_jobs_serializes_posted_at_to_iso_string(self) -> None:
        job = JobPosting(
            source="greenhouse",
            external_id="123",
            company="Example",
            title="Backend Engineer",
            location="Remote",
            link="https://example.com/jobs/123",
            posted_at=datetime(2026, 4, 29, 0, 30, tzinfo=UTC),
        )
        recorder: dict = {}
        store = FirebaseSeenJobsStore.__new__(FirebaseSeenJobsStore)
        store.root = _FakeFirebaseRoot(recorder)

        store.save_job(job)

        self.assertEqual(recorder["payload"]["posted_at"], "2026-04-29T00:30:00+00:00")
        self.assertEqual(recorder["payload"]["dedupe_key"], job.dedupe_key)

    def test_sqlite_seen_jobs_list_and_status_work_together(self) -> None:
        db_path = Path(__file__).resolve().parent / ".test-jobs.db"
        if db_path.exists():
            db_path.unlink()
        try:
            seen_store = SQLiteSeenJobsStore(db_path)
            status_store = SQLiteJobStatusStore(db_path)
            job = JobPosting(
                source="lever",
                external_id="abc123",
                company="Acme",
                title="Software Engineer I",
                location="Phoenix, AZ",
                link="https://jobs.example.com/abc123",
            )

            seen_store.save_job(job)
            status_store.set_status(job.dedupe_key, "applied")
            seen_jobs = seen_store.list_seen_jobs()
            status = status_store.get_status(job.dedupe_key)

            self.assertEqual(len(seen_jobs), 1)
            self.assertEqual(seen_jobs[0].dedupe_key, job.dedupe_key)
            self.assertIsNotNone(status)
            assert status is not None
            self.assertEqual(status.status, "applied")
            self.assertEqual(status.company, "Acme")
        finally:
            if "seen_store" in locals():
                seen_store.conn.close()
            if "status_store" in locals():
                status_store.conn.close()
            if db_path.exists():
                db_path.unlink()

    def test_sqlite_store_reads_old_rows_without_new_columns(self) -> None:
        db_path = Path(__file__).resolve().parent / ".legacy-jobs.db"
        if db_path.exists():
            db_path.unlink()
        try:
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE seen_jobs (
                    dedupe_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT NOT NULL,
                    link TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO seen_jobs (dedupe_key, source, external_id, company, title, location, link, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "greenhouse:legacy-1",
                    "greenhouse",
                    "legacy-1",
                    "Legacy Co",
                    "Software Engineer I",
                    "Remote",
                    "https://example.com/legacy-1",
                    "2026-04-29 00:00:00",
                ),
            )
            conn.commit()
            conn.close()

            seen_store = SQLiteSeenJobsStore(db_path)
            jobs = seen_store.list_seen_jobs()

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].company, "Legacy Co")
            self.assertIsNone(jobs[0].resolved_apply_url)
            self.assertIsNone(jobs[0].rank_reason)
        finally:
            if "seen_store" in locals():
                seen_store.conn.close()
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
