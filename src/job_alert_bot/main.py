from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Iterable

from .config import load_config, validate_notification_config
from .db import build_seen_jobs_store
from .filters import RankingResult, evaluate_job, location_priority
from .links import resolve_job_links
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
        enriched_job = _prepare_job(job, client, config)
        if _run_duplicate_key(enriched_job) in seen_run_keys:
            continue
        if store.is_seen(enriched_job):
            continue
        exclusion_flags = {flag.strip() for flag in (enriched_job.exclusion_flags or "").split(",") if flag.strip()}
        if exclusion_flags or (enriched_job.rank_score or 0) < config.min_match_score:
            continue

        store.save_job(enriched_job)
        seen_run_keys.add(_run_duplicate_key(enriched_job))
        if _is_fresh_job(enriched_job, config.fresh_window_minutes):
            fresh_jobs.append(enriched_job)
        else:
            digest_jobs.append(enriched_job)
        logging.info(
            "New match: %s | %s | %s | score=%s | apply=%s",
            enriched_job.company,
            enriched_job.title,
            enriched_job.original_job_url,
            enriched_job.rank_score,
            enriched_job.best_apply_url,
        )

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


def _prepare_job(job: JobPosting, client: SourceClient, config) -> JobPosting:
    resolved = resolve_job_links(job, client, config)
    resolved = replace(
        resolved,
        company_priority=config.company_priority_overrides.get(resolved.company.strip().lower(), 0),
    )
    return _apply_ranking(resolved, _evaluate(resolved, config))


def _evaluate(job: JobPosting, config) -> RankingResult:
    return evaluate_job(
        job,
        include_keywords=config.include_keywords,
        exclude_keywords=config.exclude_keywords,
        preferred_locations=config.preferred_locations,
        company_priorities=config.company_priority_overrides,
        fresh_window_minutes=config.fresh_window_minutes,
    )


def _apply_ranking(job: JobPosting, ranking: RankingResult) -> JobPosting:
    company_priority = job.company_priority
    if company_priority is None:
        company_priority = 0
    return replace(
        job,
        rank_score=ranking.score,
        rank_reason=ranking.reason,
        exclusion_flags=", ".join(ranking.exclusion_flags) if ranking.exclusion_flags else None,
        seniority_hint=ranking.seniority_hint,
        work_mode=ranking.work_mode,
        company_priority=company_priority,
    )
