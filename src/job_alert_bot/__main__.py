from __future__ import annotations

import argparse

from .config import AppConfig
from .db import build_job_status_store, build_seen_jobs_store
from .models import APPLICATION_STATUSES, JobApplicationStatus


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m job_alert_bot")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run the scheduled job check once.")

    seen_parser = subparsers.add_parser("seen", help="Inspect tracked jobs that have already been seen.")
    seen_subparsers = seen_parser.add_subparsers(dest="seen_command", required=True)
    seen_subparsers.add_parser("list", help="List seen jobs with dedupe keys and any saved status.")

    status_parser = subparsers.add_parser("status", help="Get or update application tracking statuses.")
    status_subparsers = status_parser.add_subparsers(dest="status_command", required=True)

    set_parser = status_subparsers.add_parser("set", help="Set a status for a tracked job dedupe key.")
    set_parser.add_argument("dedupe_key", help="Job dedupe key, usually in the form source:external_id")
    set_parser.add_argument("status", choices=APPLICATION_STATUSES, help="New application status value.")

    get_parser = status_subparsers.add_parser("get", help="Show the current status for one dedupe key.")
    get_parser.add_argument("dedupe_key", help="Job dedupe key, usually in the form source:external_id")

    list_parser = status_subparsers.add_parser("list", help="List saved application statuses.")
    list_parser.add_argument("--status", choices=APPLICATION_STATUSES, help="Optional status filter.")

    return parser


def _status_config() -> AppConfig:
    config = AppConfig()
    if config.storage_mode not in {"sqlite", "firebase"}:
        raise SystemExit("JOB_ALERT_STORAGE_MODE must be either 'sqlite' or 'firebase'.")
    if config.storage_mode == "firebase":
        if not config.firebase_database_url or not config.firebase_service_account_json:
            raise SystemExit(
                "Firebase status storage requires FIREBASE_DATABASE_URL and FIREBASE_SERVICE_ACCOUNT_JSON."
            )
    return config


def _print_status(record: JobApplicationStatus) -> None:
    print(f"dedupe_key: {record.dedupe_key}")
    print(f"status: {record.status}")
    print(f"updated_at: {record.updated_at.isoformat()}")
    if record.company:
        print(f"company: {record.company}")
    if record.title:
        print(f"title: {record.title}")
    if record.location:
        print(f"location: {record.location}")
    if record.link:
        print(f"link: {record.link}")


def _handle_status_command(args: argparse.Namespace) -> int:
    store = build_job_status_store(_status_config())

    if args.status_command == "set":
        record = store.set_status(args.dedupe_key, args.status)
        _print_status(record)
        return 0

    if args.status_command == "get":
        record = store.get_status(args.dedupe_key)
        if record is None:
            print(f"No saved status for {args.dedupe_key}")
            return 0
        _print_status(record)
        return 0

    records = store.list_statuses(args.status)
    if not records:
        print("No saved statuses found.")
        return 0

    for record in records:
        summary = " | ".join(
            item
            for item in (
                record.updated_at.isoformat(),
                record.status,
                record.company,
                record.title,
                record.location,
                record.dedupe_key,
            )
            if item
        )
        print(summary)
    return 0


def _handle_seen_command(args: argparse.Namespace) -> int:
    config = _status_config()
    seen_store = build_seen_jobs_store(config)
    status_store = build_job_status_store(config)
    statuses = {record.dedupe_key: record.status for record in status_store.list_statuses()}
    jobs = seen_store.list_seen_jobs()

    if not jobs:
        print("No seen jobs found.")
        return 0

    for job in jobs:
        current_status = statuses.get(job.dedupe_key, "-")
        print(
            " | ".join(
                (
                    current_status,
                    job.company,
                    job.title,
                    job.location,
                    job.dedupe_key,
                )
            )
        )
    return 0


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command in {None, "run"}:
        from .main import main

        raise SystemExit(main())

    if args.command == "status":
        raise SystemExit(_handle_status_command(args))

    if args.command == "seen":
        raise SystemExit(_handle_seen_command(args))

    raise SystemExit(parser.format_help())
