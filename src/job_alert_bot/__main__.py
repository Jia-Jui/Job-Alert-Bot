from __future__ import annotations

import argparse

from .config import AppConfig, load_app_config
from .db import build_job_status_store, build_seen_jobs_store
from .models import APPLICATION_STATUSES, JobApplicationStatus
from .review import ACTIVE_PIPELINE_STATUSES, build_review_queue, group_status_board, normalize_status_alias
from .webapp import DEFAULT_UI_HOST, DEFAULT_UI_PORT, serve_dashboard


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m job_alert_bot")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run the scheduled job check once.")

    ui_parser = subparsers.add_parser("ui", help="Run the local click-based review interface.")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_command", required=True)
    serve_parser = ui_subparsers.add_parser("serve", help="Serve the local review dashboard.")
    serve_parser.add_argument("--host", default=DEFAULT_UI_HOST, help="Host address for the local UI server.")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_UI_PORT, help="Port for the local UI server.")

    seen_parser = subparsers.add_parser("seen", help="Inspect tracked jobs that have already been seen.")
    seen_subparsers = seen_parser.add_subparsers(dest="seen_command", required=True)
    seen_subparsers.add_parser("list", help="List seen jobs with dedupe keys and any saved status.")

    queue_parser = subparsers.add_parser("queue", help="Review manual application queues.")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command", required=True)
    review_parser = queue_subparsers.add_parser("review", help="List jobs older than an hour that are not applied yet.")
    review_parser.add_argument(
        "--min-age-minutes",
        type=int,
        default=60,
        help="Only show jobs whose posted_at or first_seen_at is at least this old.",
    )

    status_parser = subparsers.add_parser("status", help="Get or update application tracking statuses.")
    status_subparsers = status_parser.add_subparsers(dest="status_command", required=True)

    set_parser = status_subparsers.add_parser("set", help="Set a status for a tracked job dedupe key.")
    set_parser.add_argument("dedupe_key", help="Job dedupe key, usually in the form source:external_id")
    set_parser.add_argument("status", choices=APPLICATION_STATUSES, help="New application status value.")

    get_parser = status_subparsers.add_parser("get", help="Show the current status for one dedupe key.")
    get_parser.add_argument("dedupe_key", help="Job dedupe key, usually in the form source:external_id")

    list_parser = status_subparsers.add_parser("list", help="List saved application statuses.")
    list_parser.add_argument("--status", choices=APPLICATION_STATUSES, help="Optional status filter.")

    status_subparsers.add_parser("board", help="Show all statuses grouped into a simple board.")
    status_subparsers.add_parser("active", help="Show active pipeline jobs such as applied and interview.")

    for alias in ("saved", "applied", "interview", "in-progress", "rejected", "offer", "closed"):
        alias_parser = status_subparsers.add_parser(alias, help=f"Shortcut for setting status to {alias}.")
        alias_parser.add_argument("dedupe_key", help="Job dedupe key, usually in the form source:external_id")

    return parser


def _status_config() -> AppConfig:
    config = load_app_config()
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

    if args.status_command in {"saved", "applied", "interview", "in-progress", "rejected", "offer", "closed"}:
        record = store.set_status(args.dedupe_key, normalize_status_alias(args.status_command))
        _print_status(record)
        return 0

    if args.status_command == "get":
        record = store.get_status(args.dedupe_key)
        if record is None:
            print(f"No saved status for {args.dedupe_key}")
            return 0
        _print_status(record)
        return 0

    if args.status_command == "board":
        grouped = group_status_board(store.list_statuses())
        printed_any = False
        for status_name in APPLICATION_STATUSES:
            records = grouped.get(status_name, [])
            if not records:
                continue
            printed_any = True
            print(f"[{status_name}]")
            for record in records:
                print(
                    " | ".join(
                        item
                        for item in (
                            record.updated_at.isoformat(),
                            record.company,
                            record.title,
                            record.location,
                            record.dedupe_key,
                        )
                        if item
                    )
                )
        if not printed_any:
            print("No saved statuses found.")
        return 0

    if args.status_command == "active":
        records = [record for record in store.list_statuses() if record.status in ACTIVE_PIPELINE_STATUSES]
        if not records:
            print("No active pipeline jobs found.")
            return 0
        for record in records:
            print(
                " | ".join(
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
            )
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


def _handle_queue_command(args: argparse.Namespace) -> int:
    config = _status_config()
    seen_store = build_seen_jobs_store(config)
    status_store = build_job_status_store(config)
    statuses = {record.dedupe_key: record for record in status_store.list_statuses()}
    queue = build_review_queue(
        jobs=seen_store.list_seen_jobs(),
        statuses=statuses,
        include_keywords=config.include_keywords,
        preferred_locations=config.preferred_locations,
        minimum_age_minutes=args.min_age_minutes,
    )

    if not queue:
        print("No review-queue jobs found.")
        return 0

    for item in queue:
        print(
            " | ".join(
                (
                    item.status or "-",
                    f"score={item.score}",
                    f"age={item.age_minutes}m" if item.age_minutes is not None else "age=?",
                    item.job.company,
                    item.job.title,
                    item.job.location,
                    item.job.dedupe_key,
                    item.job.link,
                )
            )
        )
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


def _handle_ui_command(args: argparse.Namespace) -> int:
    config = _status_config()
    serve_dashboard(config, host=args.host, port=args.port)
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

    if args.command == "queue":
        raise SystemExit(_handle_queue_command(args))

    if args.command == "ui":
        raise SystemExit(_handle_ui_command(args))

    raise SystemExit(parser.format_help())
