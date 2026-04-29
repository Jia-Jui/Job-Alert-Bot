from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_INCLUDE_KEYWORDS = [
    "software engineer",
    "backend",
    "python",
    "aws",
    "api",
    "serverless",
    "full stack",
    "entry level",
    "new grad",
    "junior",
]

DEFAULT_EXCLUDE_KEYWORDS = [
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
    "architect",
    "5+ years",
    "6+ years",
    "7+ years",
    "frontend",
    "ios",
    "android",
    "mobile",
    "react native",
    "security",
    "cyber",
    "qa",
    "sdet",
    "test engineer",
    "data scientist",
    "machine learning",
    "ml engineer",
    "devops",
    "site reliability",
    "sre",
    "clearance",
    "citizenship required",
]

DEFAULT_GITHUB_READMES = [
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    "https://raw.githubusercontent.com/ambicuity/New-Grad-Jobs/main/README.md",
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Software-Engineering-Positions/main/README.md",
]

DEFAULT_PREFERRED_LOCATIONS = [
    "phoenix",
    "scottsdale",
    "tempe",
    "mesa",
    "arizona",
    "az",
    "remote",
    "california",
    "ca",
    "seattle",
    "washington",
    "texas",
    "tx",
]


@dataclass
class AppConfig:
    companies_file: Path = Path(os.getenv("JOB_ALERT_COMPANIES_FILE", "companies.json"))
    enabled: bool = os.getenv("JOB_ALERT_ENABLED", "true").strip().lower() != "false"
    storage_mode: str = os.getenv("JOB_ALERT_STORAGE_MODE", "sqlite").strip().lower()
    sqlite_db_path: Path = Path(os.getenv("JOB_ALERT_SQLITE_DB_PATH", "jobs.db"))
    notification_channel: str = os.getenv("JOB_ALERT_NOTIFICATION_CHANNEL", "telegram").strip().lower()
    firebase_database_url: str = os.getenv("FIREBASE_DATABASE_URL", "")
    firebase_service_account_json: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    email_smtp_host: str = os.getenv("EMAIL_SMTP_HOST", "")
    email_smtp_port: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    email_smtp_username: str = os.getenv("EMAIL_SMTP_USERNAME", "")
    email_smtp_password: str = os.getenv("EMAIL_SMTP_PASSWORD", "")
    email_from_address: str = os.getenv("EMAIL_FROM_ADDRESS", "")
    email_to_address: str = os.getenv("EMAIL_TO_ADDRESS", "")
    email_use_tls: bool = os.getenv("EMAIL_USE_TLS", "true").strip().lower() != "false"
    fresh_window_minutes: int = int(os.getenv("JOB_ALERT_FRESH_WINDOW_MINUTES", "60"))
    min_match_score: int = int(os.getenv("JOB_ALERT_MIN_MATCH_SCORE", "4"))
    preferred_locations: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    request_delay_seconds: float = float(os.getenv("JOB_ALERT_REQUEST_DELAY_SECONDS", "1.5"))
    timeout_seconds: int = int(os.getenv("JOB_ALERT_TIMEOUT_SECONDS", "20"))


def _split_keywords(env_name: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(env_name, "")
    if not raw.strip():
        return defaults
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def load_config() -> tuple[AppConfig, dict]:
    config = AppConfig(
        preferred_locations=_split_keywords("JOB_ALERT_PREFERRED_LOCATIONS", DEFAULT_PREFERRED_LOCATIONS),
        include_keywords=_split_keywords("JOB_ALERT_INCLUDE_KEYWORDS", DEFAULT_INCLUDE_KEYWORDS),
        exclude_keywords=_split_keywords("JOB_ALERT_EXCLUDE_KEYWORDS", DEFAULT_EXCLUDE_KEYWORDS),
    )

    if not config.companies_file.exists():
        raise FileNotFoundError(
            f"Companies config not found: {config.companies_file}. Copy companies.example.json to companies.json first."
        )

    data = json.loads(config.companies_file.read_text(encoding="utf-8"))
    data.setdefault("lever", [])
    data.setdefault("greenhouse", [])

    github_urls = data.get("github_raw_readmes")
    if not github_urls:
        github_env = os.getenv("JOB_ALERT_GITHUB_RAW_URLS", "")
        if github_env.strip():
            data["github_raw_readmes"] = [item.strip() for item in github_env.split(",") if item.strip()]
        else:
            data["github_raw_readmes"] = DEFAULT_GITHUB_READMES

    return config, data


def validate_notification_config(config: AppConfig) -> None:
    if config.storage_mode not in {"sqlite", "firebase"}:
        raise ValueError("JOB_ALERT_STORAGE_MODE must be either 'sqlite' or 'firebase'.")

    if config.storage_mode == "firebase":
        if not config.firebase_database_url or not config.firebase_service_account_json:
            raise ValueError(
                "Firebase storage selected, but FIREBASE_DATABASE_URL or FIREBASE_SERVICE_ACCOUNT_JSON is missing."
            )

    if config.notification_channel not in {"telegram", "email"}:
        raise ValueError("JOB_ALERT_NOTIFICATION_CHANNEL must be either 'telegram' or 'email'.")

    if config.notification_channel == "telegram":
        if not config.telegram_bot_token or not config.telegram_chat_id:
            raise ValueError(
                "Telegram notifications selected, but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing."
            )
        return

    required_email_values = [
        config.email_smtp_host,
        config.email_smtp_username,
        config.email_smtp_password,
        config.email_from_address,
        config.email_to_address,
    ]
    if any(not value for value in required_email_values):
        raise ValueError(
            "Email notifications selected, but one or more email settings are missing: "
            "EMAIL_SMTP_HOST, EMAIL_SMTP_USERNAME, EMAIL_SMTP_PASSWORD, EMAIL_FROM_ADDRESS, EMAIL_TO_ADDRESS."
        )
