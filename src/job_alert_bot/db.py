from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .config import AppConfig
from .models import JobPosting


class SeenJobsStore(Protocol):
    def is_seen(self, job: JobPosting) -> bool:
        ...

    def save_job(self, job: JobPosting) -> None:
        ...


class SQLiteSeenJobsStore:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
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
        self.conn.commit()

    def is_seen(self, job: JobPosting) -> bool:
        row = self.conn.execute("SELECT 1 FROM seen_jobs WHERE dedupe_key = ?", (job.dedupe_key,)).fetchone()
        return row is not None

    def save_job(self, job: JobPosting) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_jobs (
                dedupe_key, source, external_id, company, title, location, link
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job.dedupe_key, job.source, job.external_id, job.company, job.title, job.location, job.link),
        )
        self.conn.commit()


class FirebaseSeenJobsStore:
    def __init__(self, config: AppConfig) -> None:
        import firebase_admin
        from firebase_admin import credentials, db

        if not firebase_admin._apps:
            service_account = json.loads(config.firebase_service_account_json)
            firebase_admin.initialize_app(
                credentials.Certificate(service_account),
                {"databaseURL": config.firebase_database_url},
            )
        self.root = db.reference("/seen_jobs")

    def is_seen(self, job: JobPosting) -> bool:
        return self.root.child(_firebase_key(job.dedupe_key)).get() is not None

    def save_job(self, job: JobPosting) -> None:
        payload = asdict(job)
        payload["dedupe_key"] = job.dedupe_key
        self.root.child(_firebase_key(job.dedupe_key)).set(payload)


def build_seen_jobs_store(config: AppConfig) -> SeenJobsStore:
    if config.storage_mode == "firebase":
        return FirebaseSeenJobsStore(config)
    return SQLiteSeenJobsStore(config.sqlite_db_path)


def _firebase_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
