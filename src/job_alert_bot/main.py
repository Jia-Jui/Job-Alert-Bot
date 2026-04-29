from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Iterable

from .config import load_config, validate_notification_config
from .db import build_seen_jobs_store
from .filters import location_priority, match_score, matches_keywords
from .models import JobPosting
from .notifiers.email import send_email_alert, send_email_digest
from .notifiers.telegram import send_telegram_alert
from .sources.base import SourceClient
from .sources.github_readme import fetch_jobs_from_readme
from .sources.greenhouse import fetch_greenhouse_jobs
from .sources.lever import fetch_lever_jobs


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> int:
    config, source_config = load_config()
    if not config.enabled:
        logging.info("Job Alert Bot is disabled. Exiting without checking sources.")
        return 0
    validate_notification_config(config)
    store = build_seen_jobs_store(config)
    client = SourceClient(
        timeout_seconds=config.timeout_seconds,
        request_delay_seconds=config.request_delay_seconds,
    )

    jobs = list(_collect_jobs(client, source_config))
    logging.info("Collected %s jobs before filtering", len(jobs))

    fresh_jobs: list[JobPosting] = []
    digest_jobs: list[JobPosting] = []
    seen_run_keys: set[str] = set()

    for job in jobs:
        if not matches_keywords(job, config.include_keywords, config.exclude_keywords):
            continue
        if match_score(job, config.include_keywords, config.preferred_locations) < config.min_match_score:
            continue
        if store.is_seen(job):
            continue
        if _run_duplicate_key(job) in seen_run_keys:
            continue

        store.save_job(job)
        seen_run_keys.add(_run_duplicate_key(job))
        if _is_fresh_job(job, config.fresh_window_minutes):
            fresh_jobs.append(job)
        else:
            digest_jobs.append(job)
        logging.info("New match: %s | %s | %s", job.company, job.title, job.link)

    fresh_jobs.sort(key=lambda job: location_priority(job, config.preferred_locations))
    digest_jobs.sort(key=lambda job: location_priority(job, config.preferred_locations))

    for job in fresh_jobs:
        _send_notification(config, job)

    if digest_jobs:
        _send_digest_notification(config, digest_jobs)

    new_matches = len(fresh_jobs) + len(digest_jobs)
    logging.info("Finished. New matches: %s", new_matches)
    return 0


def _collect_jobs(client: SourceClient, source_config: dict) -> Iterable[JobPosting]:
    for target in source_config.get("lever", []):
        company = target["company"]
        slug = target["slug"]
        logging.info("Checking Lever board for %s", company)
        try:
            yield from fetch_lever_jobs(client, company, slug)
        except Exception as exc:
            logging.warning("Lever source failed for %s: %s", company, exc)

    for target in source_config.get("greenhouse", []):
        company = target["company"]
        board_token = target["board_token"]
        logging.info("Checking Greenhouse board for %s", company)
        try:
            yield from fetch_greenhouse_jobs(client, company, board_token)
        except Exception as exc:
            logging.warning("Greenhouse source failed for %s: %s", company, exc)

    for raw_readme_url in source_config.get("github_raw_readmes", []):
        logging.info("Checking GitHub README source %s", raw_readme_url)
        try:
            yield from fetch_jobs_from_readme(client, raw_readme_url)
        except Exception as exc:
            logging.warning("GitHub README source failed for %s: %s", raw_readme_url, exc)


def _send_notification(config, job: JobPosting) -> None:
    if config.notification_channel == "telegram":
        send_telegram_alert(
            config.telegram_bot_token,
            config.telegram_chat_id,
            job,
            config.timeout_seconds,
        )
        return

    send_email_alert(config, job)


def _send_digest_notification(config, jobs: list[JobPosting]) -> None:
    if config.notification_channel == "telegram":
        for job in jobs:
            send_telegram_alert(
                config.telegram_bot_token,
                config.telegram_chat_id,
                job,
                config.timeout_seconds,
            )
        return

    send_email_digest(config, jobs)


def _is_fresh_job(job: JobPosting, fresh_window_minutes: int) -> bool:
    if job.posted_at is None:
        return False
    return job.posted_at >= datetime.now(UTC) - timedelta(minutes=fresh_window_minutes)


def _run_duplicate_key(job: JobPosting) -> str:
    normalized_link = job.link.strip().lower().rstrip("/")
    if normalized_link:
        return normalized_link
    return job.dedupe_key
