from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from dec_calendar.config import Settings
from dec_calendar.idempotency import IdempotencyStore
from dec_calendar.jira_client import JiraClient
from dec_calendar.messages import format_alert_message, jira_alert_comment
from dec_calendar.models import AlertSlot
from dec_calendar.reminders import evaluate_issue, idempotency_key, resolve_slot
from dec_calendar.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


@dataclass
class AlertAction:
    issue_key: str
    summary: str
    window: str
    message: str
    idem_key: str


@dataclass
class JobReport:
    today: date
    slot: Optional[str] = None
    considered: int = 0
    sent: list[AlertAction] = field(default_factory=list)
    skipped_already_sent: list[str] = field(default_factory=list)
    dry_run_planned: list[AlertAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def local_today(timezone: str, *, override: Optional[date] = None) -> date:
    if override is not None:
        return override
    return datetime.now(ZoneInfo(timezone)).date()


def run_reminder_job(
    settings: Settings,
    *,
    dry_run: Optional[bool] = None,
    today: Optional[date] = None,
    slot: AlertSlot = AlertSlot.AUTO,
    jira: Optional[JiraClient] = None,
    telegram: Optional[TelegramClient] = None,
    store: Optional[IdempotencyStore] = None,
    comment_on_jira: bool = True,
    now: Optional[datetime] = None,
) -> JobReport:
    """Fetch DEC issues and send due Telegram reminders (idempotent)."""
    is_dry = settings.dry_run if dry_run is None else dry_run
    today_local = local_today(settings.timezone, override=today)
    resolved = resolve_slot(slot, timezone=settings.timezone, now=now)
    report = JobReport(today=today_local, slot=resolved.value if resolved else None)

    jira = jira or JiraClient(settings)
    store = store or IdempotencyStore.load(settings.idempotency_path)

    issues = jira.list_calendar_issues()
    issues = sorted(issues, key=lambda i: (i.due_date, i.key))
    report.considered = len(issues)
    logger.info(
        "Loaded %s calendar issues for %s slot=%s",
        len(issues),
        today_local.isoformat(),
        resolved.value if resolved else "none",
    )

    pending_telegram = telegram
    if not is_dry:
        pending_telegram = telegram or TelegramClient(settings)

    for issue in issues:
        windows = evaluate_issue(issue, today_local, slot=resolved)
        for window in windows:
            key = idempotency_key(issue.key, window, issue.due_date, today=today_local)
            if store.has(key):
                report.skipped_already_sent.append(key)
                continue
            message = format_alert_message(issue, window, today=today_local)
            action = AlertAction(
                issue_key=issue.key,
                summary=issue.summary,
                window=window.value,
                message=message,
                idem_key=key,
            )
            if is_dry:
                report.dry_run_planned.append(action)
                logger.info("[dry-run] %s %s", issue.key, window.value)
                continue
            try:
                assert pending_telegram is not None
                pending_telegram.send_message(message)
                if comment_on_jira:
                    try:
                        jira.add_comment(issue.key, jira_alert_comment(window, today_local))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Jira comment failed for %s: %s", issue.key, exc)
                store.add(key)
                report.sent.append(action)
            except Exception as exc:  # noqa: BLE001
                err = f"{issue.key}/{window.value}: {exc}"
                logger.exception("Alert failed: %s", err)
                report.errors.append(err)

    return report
