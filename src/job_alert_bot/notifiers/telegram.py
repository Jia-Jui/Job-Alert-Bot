from __future__ import annotations

import requests

from ..models import JobPosting
from .common import job_summary_lines


def send_telegram_alert(bot_token: str, chat_id: str, job: JobPosting, timeout_seconds: int) -> None:
    if not bot_token or not chat_id:
        return

    text = "New Job Match\n" + "\n".join(job_summary_lines(job))

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
