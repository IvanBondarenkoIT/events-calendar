from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    timezone: str
    jira_url: str
    jira_email: str
    jira_api_token: str
    jira_project_key: str
    jira_issue_type: str
    jira_ssl_verify: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_disable_ssl_verify: bool
    notify_hub_url: str
    notify_hub_api_key: str
    notify_via_hub: bool
    dry_run: bool
    idempotency_path: Path
    log_level: str

    def require_jira(self) -> None:
        missing = [
            name
            for name, val in [
                ("JIRA_URL", self.jira_url),
                ("JIRA_EMAIL", self.jira_email),
                ("JIRA_API_TOKEN", self.jira_api_token),
                ("JIRA_PROJECT_KEY", self.jira_project_key),
            ]
            if not val
        ]
        if missing:
            raise ValueError(f"Missing required Jira settings: {', '.join(missing)}")

    def require_telegram(self) -> None:
        missing = [
            name
            for name, val in [
                ("TELEGRAM_BOT_TOKEN", self.telegram_bot_token),
                ("TELEGRAM_CHAT_ID", self.telegram_chat_id),
            ]
            if not val
        ]
        if missing:
            raise ValueError(f"Missing required Telegram settings: {', '.join(missing)}")

    def require_notify_hub(self) -> None:
        missing = [
            name
            for name, val in [
                ("NOTIFY_HUB_URL", self.notify_hub_url),
                ("NOTIFY_HUB_API_KEY", self.notify_hub_api_key),
            ]
            if not val
        ]
        if missing:
            raise ValueError(f"Missing required Notify Hub settings: {', '.join(missing)}")

    @property
    def jira_browse_base(self) -> str:
        return self.jira_url.rstrip("/") + "/browse"


def load_settings(env_file: Optional[Path] = None) -> Settings:
    """Load settings from process env, optionally after loading a .env file."""
    if env_file is not None:
        load_dotenv(env_file, override=False)
    else:
        candidate = REPO_ROOT / ".env"
        if candidate.exists():
            load_dotenv(candidate, override=False)

    idem_raw = (os.getenv("IDEMPOTENCY_PATH") or "./data/alert_state.json").strip()
    idem_path = Path(idem_raw)
    if not idem_path.is_absolute():
        idem_path = REPO_ROOT / idem_path

    return Settings(
        timezone=(os.getenv("APP_TIMEZONE") or "Asia/Tbilisi").strip(),
        jira_url=(os.getenv("JIRA_URL") or "").strip().rstrip("/"),
        jira_email=(os.getenv("JIRA_EMAIL") or "").strip(),
        jira_api_token=(os.getenv("JIRA_API_TOKEN") or "").strip(),
        jira_project_key=(os.getenv("JIRA_PROJECT_KEY") or "DEC").strip(),
        jira_issue_type=(os.getenv("JIRA_ISSUE_TYPE") or "Task").strip(),
        jira_ssl_verify=_as_bool(os.getenv("JIRA_SSL_VERIFY"), default=True),
        telegram_bot_token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
        telegram_chat_id=(os.getenv("TELEGRAM_CHAT_ID") or "").strip(),
        telegram_disable_ssl_verify=_as_bool(
            os.getenv("TELEGRAM_DISABLE_SSL_VERIFY") or os.getenv("DISABLE_SSL_VERIFY"),
            default=False,
        ),
        notify_hub_url=(os.getenv("NOTIFY_HUB_URL") or "").strip().rstrip("/"),
        notify_hub_api_key=(os.getenv("NOTIFY_HUB_API_KEY") or "").strip(),
        notify_via_hub=_as_bool(os.getenv("NOTIFY_VIA_HUB"), default=False),
        dry_run=_as_bool(os.getenv("DRY_RUN"), default=False),
        idempotency_path=idem_path,
        log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
    )
