from __future__ import annotations

import time
from typing import Any

import requests


class SourceClient:
    def __init__(self, timeout_seconds: int, request_delay_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "job-alert-bot/0.1 (+https://github.com/Jia-Jui/Job-Alert-Bot; "
                    "public job feed checker)"
                )
            }
        )

    def get_json(self, url: str) -> Any:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        time.sleep(self.request_delay_seconds)
        return response.json()

    def get_text(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        time.sleep(self.request_delay_seconds)
        return response.text
