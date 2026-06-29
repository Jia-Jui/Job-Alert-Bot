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

    def list_seen_jobs(self) -> list[JobPosting]:
        ...

    def get_job(self, dedupe_key: str) -> JobPosting | None:
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
                posted_at TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                public_job_url TEXT,
                resolved_apply_url TEXT,
                referral_or_tracking_url TEXT,
                link_source TEXT,
                link_confidence TEXT,
                link_resolution_notes TEXT,
                rank_score INTEGER,
                rank_reason TEXT,
                exclusion_flags TEXT,
                seniority_hint TEXT,
                work_mode TEXT,
                company_priority INTEGER
            )
            """
        )
        _ensure_sqlite_column(self.conn, "seen_jobs", "posted_at", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "public_job_url", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "resolved_apply_url", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "referral_or_tracking_url", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "link_source", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "link_confidence", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "link_resolution_notes", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "rank_score", "INTEGER")
        _ensure_sqlite_column(self.conn, "seen_jobs", "rank_reason", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "exclusion_flags", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "seniority_hint", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "work_mode", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "company_priority", "INTEGER")
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
                link TEXT,
                public_job_url TEXT,
                resolved_apply_url TEXT,
                referral_or_tracking_url TEXT,
                link_confidence TEXT,
                rank_score INTEGER,
                rank_reason TEXT
            )
            """
        )
        _ensure_sqlite_column(self.conn, "job_statuses", "public_job_url", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "resolved_apply_url", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "referral_or_tracking_url", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "link_confidence", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "rank_score", "INTEGER")
        _ensure_sqlite_column(self.conn, "job_statuses", "rank_reason", "TEXT")
        self.conn.commit()

    def is_seen(self, job: JobPosting) -> bool:
        row = self.conn.execute("SELECT 1 FROM seen_jobs WHERE dedupe_key = ?", (job.dedupe_key,)).fetchone()
        return row is not None

    def save_job(self, job: JobPosting) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_jobs (
                dedupe_key, source, external_id, company, title, location, link, posted_at,
                public_job_url, resolved_apply_url, referral_or_tracking_url, link_source,
                link_confidence, link_resolution_notes, rank_score, rank_reason,
                exclusion_flags, seniority_hint, work_mode, company_priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.dedupe_key,
                job.source,
                job.external_id,
                job.company,
                job.title,
                job.location,
                job.link,
                job.posted_at.isoformat() if job.posted_at is not None else None,
                job.public_job_url,
                job.resolved_apply_url,
                job.referral_or_tracking_url,
                job.link_source,
                job.link_confidence,
                job.link_resolution_notes,
                job.rank_score,
                job.rank_reason,
                job.exclusion_flags,
                job.seniority_hint,
                job.work_mode,
                job.company_priority,
            ),
        )
        self.conn.commit()

    def list_seen_jobs(self) -> list[JobPosting]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM seen_jobs
            ORDER BY first_seen_at DESC, company, title
            """
        ).fetchall()
        return [_job_posting_from_row(row) for row in rows]

    def get_job(self, dedupe_key: str) -> JobPosting | None:
        row = self.conn.execute("SELECT * FROM seen_jobs WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        if row is None:
            return None
        return _job_posting_from_row(row)


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
                posted_at TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                public_job_url TEXT,
                resolved_apply_url TEXT,
                referral_or_tracking_url TEXT,
                link_source TEXT,
                link_confidence TEXT,
                link_resolution_notes TEXT,
                rank_score INTEGER,
                rank_reason TEXT,
                exclusion_flags TEXT,
                seniority_hint TEXT,
                work_mode TEXT,
                company_priority INTEGER
            )
            """
        )
        _ensure_sqlite_column(self.conn, "seen_jobs", "posted_at", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "public_job_url", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "resolved_apply_url", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "referral_or_tracking_url", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "link_source", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "link_confidence", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "link_resolution_notes", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "rank_score", "INTEGER")
        _ensure_sqlite_column(self.conn, "seen_jobs", "rank_reason", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "exclusion_flags", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "seniority_hint", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "work_mode", "TEXT")
        _ensure_sqlite_column(self.conn, "seen_jobs", "company_priority", "INTEGER")
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
                link TEXT,
                public_job_url TEXT,
                resolved_apply_url TEXT,
                referral_or_tracking_url TEXT,
                link_confidence TEXT,
                rank_score INTEGER,
                rank_reason TEXT
            )
            """
        )
        _ensure_sqlite_column(self.conn, "job_statuses", "public_job_url", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "resolved_apply_url", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "referral_or_tracking_url", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "link_confidence", "TEXT")
        _ensure_sqlite_column(self.conn, "job_statuses", "rank_score", "INTEGER")
        _ensure_sqlite_column(self.conn, "job_statuses", "rank_reason", "TEXT")
        self.conn.commit()

    def get_status(self, dedupe_key: str) -> JobApplicationStatus | None:
        row = self.conn.execute(
            """
            SELECT dedupe_key, status, updated_at, source, external_id, company, title, location, link,
                   public_job_url, resolved_apply_url, referral_or_tracking_url, link_confidence, rank_score, rank_reason
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
            SELECT source, external_id, company, title, location, link, public_job_url, resolved_apply_url,
                   referral_or_tracking_url, link_confidence, rank_score, rank_reason
            FROM seen_jobs
            WHERE dedupe_key = ?
            """,
            (dedupe_key,),
        ).fetchone()

        metadata = tuple(seen_row) if seen_row is not None else (None,) * 12
        self.conn.execute(
            """
            INSERT INTO job_statuses (
                dedupe_key, status, updated_at, source, external_id, company, title, location, link,
                public_job_url, resolved_apply_url, referral_or_tracking_url, link_confidence, rank_score, rank_reason
            ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP,
                source = COALESCE(excluded.source, job_statuses.source),
                external_id = COALESCE(excluded.external_id, job_statuses.external_id),
                company = COALESCE(excluded.company, job_statuses.company),
                title = COALESCE(excluded.title, job_statuses.title),
                location = COALESCE(excluded.location, job_statuses.location),
                link = COALESCE(excluded.link, job_statuses.link),
                public_job_url = COALESCE(excluded.public_job_url, job_statuses.public_job_url),
                resolved_apply_url = COALESCE(excluded.resolved_apply_url, job_statuses.resolved_apply_url),
                referral_or_tracking_url = COALESCE(excluded.referral_or_tracking_url, job_statuses.referral_or_tracking_url),
                link_confidence = COALESCE(excluded.link_confidence, job_statuses.link_confidence),
                rank_score = COALESCE(excluded.rank_score, job_statuses.rank_score),
                rank_reason = COALESCE(excluded.rank_reason, job_statuses.rank_reason)
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
            SELECT dedupe_key, status, updated_at, source, external_id, company, title, location, link,
                   public_job_url, resolved_apply_url, referral_or_tracking_url, link_confidence, rank_score, rank_reason
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
        if job.posted_at is not None:
            payload["posted_at"] = job.posted_at.isoformat()
        if job.first_seen_at is None:
            payload["first_seen_at"] = datetime.now(UTC).isoformat()
        self.root.child(_firebase_key(job.dedupe_key)).set(payload)

    def list_seen_jobs(self) -> list[JobPosting]:
        raw = self.root.get() or {}
        jobs: list[JobPosting] = []
        for payload in raw.values():
            jobs.append(_job_posting_from_payload(payload))
        jobs.sort(key=lambda item: (item.company, item.title, item.location))
        return jobs

    def get_job(self, dedupe_key: str) -> JobPosting | None:
        payload = self.root.child(_firebase_key(dedupe_key)).get()
        if payload is None:
            return None
        return _job_posting_from_payload(payload)


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
            "public_job_url": seen_payload.get("public_job_url"),
            "resolved_apply_url": seen_payload.get("resolved_apply_url"),
            "referral_or_tracking_url": seen_payload.get("referral_or_tracking_url"),
            "link_confidence": seen_payload.get("link_confidence"),
            "rank_score": seen_payload.get("rank_score"),
            "rank_reason": seen_payload.get("rank_reason"),
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
        public_job_url=payload.get("public_job_url"),
        resolved_apply_url=payload.get("resolved_apply_url"),
        referral_or_tracking_url=payload.get("referral_or_tracking_url"),
        link_confidence=payload.get("link_confidence"),
        rank_score=payload.get("rank_score"),
        rank_reason=payload.get("rank_reason"),
    )


def _job_posting_from_payload(payload: dict) -> JobPosting:
    posted_at = _parse_datetime(payload.get("posted_at"))
    return JobPosting(
        source=payload["source"],
        external_id=payload["external_id"],
        company=payload["company"],
        title=payload["title"],
        location=payload["location"],
        link=payload["link"],
        posted_at=posted_at,
        first_seen_at=_parse_datetime(payload.get("first_seen_at")),
        public_job_url=payload.get("public_job_url"),
        resolved_apply_url=payload.get("resolved_apply_url"),
        referral_or_tracking_url=payload.get("referral_or_tracking_url"),
        link_source=payload.get("link_source"),
        link_confidence=payload.get("link_confidence"),
        link_resolution_notes=payload.get("link_resolution_notes"),
        rank_score=payload.get("rank_score"),
        rank_reason=payload.get("rank_reason"),
        exclusion_flags=payload.get("exclusion_flags"),
        seniority_hint=payload.get("seniority_hint"),
        work_mode=payload.get("work_mode"),
        company_priority=payload.get("company_priority"),
    )


def _job_status_from_row(row: sqlite3.Row) -> JobApplicationStatus:
    updated_at = _parse_datetime(row["updated_at"])
    if updated_at is None:
        raise ValueError("Job status row is missing updated_at.")
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
        public_job_url=row["public_job_url"],
        resolved_apply_url=row["resolved_apply_url"],
        referral_or_tracking_url=row["referral_or_tracking_url"],
        link_confidence=row["link_confidence"],
        rank_score=row["rank_score"],
        rank_reason=row["rank_reason"],
    )


def _job_posting_from_row(row: sqlite3.Row) -> JobPosting:
    return JobPosting(
        source=row["source"],
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        link=row["link"],
        posted_at=_parse_datetime(row["posted_at"]),
        first_seen_at=_parse_datetime(row["first_seen_at"]),
        public_job_url=row["public_job_url"],
        resolved_apply_url=row["resolved_apply_url"],
        referral_or_tracking_url=row["referral_or_tracking_url"],
        link_source=row["link_source"],
        link_confidence=row["link_confidence"],
        link_resolution_notes=row["link_resolution_notes"],
        rank_score=row["rank_score"],
        rank_reason=row["rank_reason"],
        exclusion_flags=row["exclusion_flags"],
        seniority_hint=row["seniority_hint"],
        work_mode=row["work_mode"],
        company_priority=row["company_priority"],
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    if "T" in value:
        parsed = datetime.fromisoformat(value)
    else:
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _ensure_sqlite_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any(column[1] == column_name for column in columns):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
