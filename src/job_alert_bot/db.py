from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .config import AppConfig
from .models import JobApplicationStatus, JobPosting


class SeenJobsStore(Protocol):
    def is_seen(self, job: JobPosting) -> bool:
        ...

    def save_job(self, job: JobPosting) -> None:
        ...


class JobStatusStore(Protocol):
    def get_status(self, dedupe_key: str) -> JobApplicationStatus | None:
        ...

    def set_status(self, dedupe_key: str, status: str) -> JobApplicationStatus:
        ...

    def list_statuses(self, status: str | None = None) -> list[JobApplicationStatus]:
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
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_statuses (
                dedupe_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                external_id TEXT,
                company TEXT,
                title TEXT,
                location TEXT,
                link TEXT
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


class SQLiteJobStatusStore:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
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
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_statuses (
                dedupe_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                external_id TEXT,
                company TEXT,
                title TEXT,
                location TEXT,
                link TEXT
            )
            """
        )
        self.conn.commit()

    def get_status(self, dedupe_key: str) -> JobApplicationStatus | None:
        row = self.conn.execute(
            """
            SELECT dedupe_key, status, updated_at, source, external_id, company, title, location, link
            FROM job_statuses
            WHERE dedupe_key = ?
            """,
            (dedupe_key,),
        ).fetchone()
        if row is None:
            return None
        return _job_status_from_row(row)

    def set_status(self, dedupe_key: str, status: str) -> JobApplicationStatus:
        seen_row = self.conn.execute(
            """
            SELECT source, external_id, company, title, location, link
            FROM seen_jobs
            WHERE dedupe_key = ?
            """,
            (dedupe_key,),
        ).fetchone()

        metadata = tuple(seen_row) if seen_row is not None else (None, None, None, None, None, None)
        self.conn.execute(
            """
            INSERT INTO job_statuses (
                dedupe_key, status, updated_at, source, external_id, company, title, location, link
            ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP,
                source = COALESCE(excluded.source, job_statuses.source),
                external_id = COALESCE(excluded.external_id, job_statuses.external_id),
                company = COALESCE(excluded.company, job_statuses.company),
                title = COALESCE(excluded.title, job_statuses.title),
                location = COALESCE(excluded.location, job_statuses.location),
                link = COALESCE(excluded.link, job_statuses.link)
            """,
            (dedupe_key, status, *metadata),
        )
        self.conn.commit()
        record = self.get_status(dedupe_key)
        if record is None:
            raise RuntimeError(f"Failed to persist job status for {dedupe_key}.")
        return record

    def list_statuses(self, status: str | None = None) -> list[JobApplicationStatus]:
        query = """
            SELECT dedupe_key, status, updated_at, source, external_id, company, title, location, link
            FROM job_statuses
        """
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC, company, title"

        rows = self.conn.execute(query, params).fetchall()
        return [_job_status_from_row(row) for row in rows]


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


class FirebaseJobStatusStore:
    def __init__(self, config: AppConfig) -> None:
        import firebase_admin
        from firebase_admin import credentials, db

        if not firebase_admin._apps:
            service_account = json.loads(config.firebase_service_account_json)
            firebase_admin.initialize_app(
                credentials.Certificate(service_account),
                {"databaseURL": config.firebase_database_url},
            )
        self.status_root = db.reference("/job_statuses")
        self.seen_root = db.reference("/seen_jobs")

    def get_status(self, dedupe_key: str) -> JobApplicationStatus | None:
        payload = self.status_root.child(_firebase_key(dedupe_key)).get()
        if payload is None:
            return None
        return _job_status_from_payload(dedupe_key, payload)

    def set_status(self, dedupe_key: str, status: str) -> JobApplicationStatus:
        seen_payload = self.seen_root.child(_firebase_key(dedupe_key)).get() or {}
        payload = {
            "dedupe_key": dedupe_key,
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
            "source": seen_payload.get("source"),
            "external_id": seen_payload.get("external_id"),
            "company": seen_payload.get("company"),
            "title": seen_payload.get("title"),
            "location": seen_payload.get("location"),
            "link": seen_payload.get("link"),
        }
        self.status_root.child(_firebase_key(dedupe_key)).update(payload)
        record = self.get_status(dedupe_key)
        if record is None:
            raise RuntimeError(f"Failed to persist job status for {dedupe_key}.")
        return record

    def list_statuses(self, status: str | None = None) -> list[JobApplicationStatus]:
        raw = self.status_root.get() or {}
        records: list[JobApplicationStatus] = []
        for payload in raw.values():
            dedupe_key = payload.get("dedupe_key")
            if not dedupe_key:
                continue
            record = _job_status_from_payload(dedupe_key, payload)
            if status is not None and record.status != status:
                continue
            records.append(record)
        records.sort(key=lambda item: (item.updated_at, item.company or "", item.title or ""), reverse=True)
        return records


def build_seen_jobs_store(config: AppConfig) -> SeenJobsStore:
    if config.storage_mode == "firebase":
        return FirebaseSeenJobsStore(config)
    return SQLiteSeenJobsStore(config.sqlite_db_path)


def build_job_status_store(config: AppConfig) -> JobStatusStore:
    if config.storage_mode == "firebase":
        return FirebaseJobStatusStore(config)
    return SQLiteJobStatusStore(config.sqlite_db_path)


def _firebase_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _job_status_from_payload(dedupe_key: str, payload: dict) -> JobApplicationStatus:
    updated_at_raw = payload["updated_at"]
    return JobApplicationStatus(
        dedupe_key=payload.get("dedupe_key", dedupe_key),
        status=payload["status"],
        updated_at=datetime.fromisoformat(updated_at_raw),
        source=payload.get("source"),
        external_id=payload.get("external_id"),
        company=payload.get("company"),
        title=payload.get("title"),
        location=payload.get("location"),
        link=payload.get("link"),
    )


def _job_status_from_row(row: sqlite3.Row) -> JobApplicationStatus:
    updated_at_raw = row["updated_at"]
    if "T" in updated_at_raw:
        updated_at = datetime.fromisoformat(updated_at_raw)
    else:
        updated_at = datetime.fromisoformat(updated_at_raw.replace(" ", "T"))
    return JobApplicationStatus(
        dedupe_key=row["dedupe_key"],
        status=row["status"],
        updated_at=updated_at,
        source=row["source"],
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        link=row["link"],
    )
