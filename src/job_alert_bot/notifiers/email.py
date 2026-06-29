from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import AppConfig
from ..models import JobPosting
from .common import job_summary_lines


def send_email_alert(config: AppConfig, job: JobPosting) -> None:
    message = EmailMessage()
    message["Subject"] = f"New Job Match: {job.company} - {job.title}"
    message["From"] = config.email_from_address
    message["To"] = config.email_to_address
    message.set_content("New Job Match\n" + "\n".join(job_summary_lines(job)) + "\n")

    with smtplib.SMTP(config.email_smtp_host, config.email_smtp_port, timeout=config.timeout_seconds) as server:
        if config.email_use_tls:
            server.starttls()
        server.login(config.email_smtp_username, config.email_smtp_password)
        server.send_message(message)


def send_email_digest(config: AppConfig, jobs: list[JobPosting]) -> None:
    if not jobs:
        return

    message = EmailMessage()
    message["Subject"] = f"Job Alert Digest: {len(jobs)} older matches"
    message["From"] = config.email_from_address
    message["To"] = config.email_to_address

    lines = ["Job Alert Digest", "", f"Found {len(jobs)} older or backlog matches:", ""]
    for index, job in enumerate(jobs, start=1):
        lines.append(f"{index}. {job.company} - {job.title}")
        for detail in job_summary_lines(job)[2:]:
            lines.append(f"   {detail}")
        lines.append("")

    message.set_content("\n".join(lines).strip() + "\n")

    with smtplib.SMTP(config.email_smtp_host, config.email_smtp_port, timeout=config.timeout_seconds) as server:
        if config.email_use_tls:
            server.starttls()
        server.login(config.email_smtp_username, config.email_smtp_password)
        server.send_message(message)
