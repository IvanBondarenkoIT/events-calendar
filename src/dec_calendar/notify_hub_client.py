from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

import requests

from dec_calendar.config import Settings
from dec_calendar.models import AlertSlot, JiraCalendarIssue, ReminderWindow

logger = logging.getLogger(__name__)

CALENDAR_EVENT_TYPE = "calendar.event.v1"
CALENDAR_REMINDER_TYPE = "calendar.reminder.v1"
CALENDAR_SOURCE = "events-calendar"

NAG_WINDOWS = {
    ReminderWindow.NAG_START_WORK_MORNING,
    ReminderWindow.NAG_START_WORK_EVENING,
    ReminderWindow.NAG_FINISH_DONE_MORNING,
}


class NotifyHubError(RuntimeError):
    pass


def hub_event_type(window: ReminderWindow) -> str:
    """Nags are calendar.reminder.v1; one-shot holiday/promo/birthday stay calendar.event.v1."""
    if window in NAG_WINDOWS:
        return CALENDAR_REMINDER_TYPE
    return CALENDAR_EVENT_TYPE


def calendar_event_id(idem_key: str) -> str:
    """Stable hub event_id: calendar- + local idempotency key."""
    return f"calendar-{idem_key}"


def seed_chat_ids(telegram_chat_id: str) -> list[int]:
    raw = (telegram_chat_id or "").strip()
    if not raw:
        return []
    try:
        return [int(raw)]
    except ValueError as exc:
        raise NotifyHubError(f"TELEGRAM_CHAT_ID is not an int: {raw!r}") from exc


def build_calendar_event(
    *,
    idem_key: str,
    issue: JiraCalendarIssue,
    window: ReminderWindow,
    body: str,
    today: date,
    slot: Optional[AlertSlot] = None,
    seed_chat_id: str = "",
) -> dict[str, Any]:
    return {
        "event_id": calendar_event_id(idem_key),
        "type": hub_event_type(window),
        "severity": "info",
        "source": CALENDAR_SOURCE,
        "title": issue.summary,
        "body": body,
        "channels": ["public"],
        "targets": {"chat_ids": seed_chat_ids(seed_chat_id), "user_ids": []},
        "require_ack": False,
        "data": {
            "jira_key": issue.key,
            "window": window.value,
            "due_date": issue.due_date.isoformat(),
            "slot": slot.value if slot is not None else None,
            "kind": issue.kind.value,
            "today": today.isoformat(),
        },
    }


class NotifyHubClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_notify_hub()
        self.base_url = settings.notify_hub_url.rstrip("/")
        self.api_key = settings.notify_hub_api_key

    def post_event(self, event: dict[str, Any], *, timeout_s: int = 20) -> dict[str, Any]:
        event_id = str(event.get("event_id") or "")
        if not event_id:
            raise NotifyHubError("event_id is required")
        url = f"{self.base_url}/v1/events"
        try:
            response = requests.post(
                url,
                json=event,
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key,
                    "Accept": "application/json",
                },
                timeout=timeout_s,
            )
        except requests.RequestException as exc:
            raise NotifyHubError(f"Notify Hub request failed: {exc}") from exc

        if response.status_code == 401:
            raise NotifyHubError("Notify Hub authentication failed — check NOTIFY_HUB_API_KEY")
        if response.status_code >= 400:
            raise NotifyHubError(
                f"Notify Hub HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json() if response.content else {}
        except ValueError as exc:
            raise NotifyHubError("Notify Hub returned non-JSON body") from exc
        if not isinstance(payload, dict):
            raise NotifyHubError("Notify Hub returned unexpected JSON")
        status = str(payload.get("status") or "")
        if status not in {"accepted", "duplicate"}:
            raise NotifyHubError(f"Notify Hub unexpected status={status!r}")
        logger.info("Notify Hub %s event_id=%s", status, event_id)
        return payload
