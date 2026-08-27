from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from dec_calendar.models import (
    AlertSlot,
    EventKind,
    JiraCalendarIssue,
    ReminderWindow,
    StatusCategory,
)

# Holiday / promo one-shot windows (days before due date).
HOLIDAY_WINDOWS: tuple[tuple[ReminderWindow, int], ...] = (
    (ReminderWindow.T_MINUS_30, 30),
    (ReminderWindow.T_MINUS_15, 15),
)

# Birthday windows.
BIRTHDAY_WINDOWS: tuple[tuple[ReminderWindow, int], ...] = (
    (ReminderWindow.T_MINUS_1, 1),
    (ReminderWindow.T_MINUS_0, 0),
)

# Workflow nags (holiday/promo only).
START_WORK_MAX_DAYS = 30
FINISH_DONE_MAX_DAYS = 5
MORNING_HOUR = 10
EVENING_HOUR = 22


def windows_for_kind(kind: EventKind) -> tuple[tuple[ReminderWindow, int], ...]:
    if kind is EventKind.BIRTHDAY:
        return BIRTHDAY_WINDOWS
    return HOLIDAY_WINDOWS


def days_until_due(due: date, today: date) -> int:
    return (due - today).days


def resolve_slot(
    slot: AlertSlot,
    *,
    timezone: str,
    now: Optional[datetime] = None,
) -> Optional[AlertSlot]:
    """Map AUTO to morning/evening by local hour; None if outside scheduled hours."""
    if slot is AlertSlot.MORNING or slot is AlertSlot.EVENING:
        return slot
    local = now or datetime.now(ZoneInfo(timezone))
    if local.tzinfo is None:
        local = local.replace(tzinfo=ZoneInfo(timezone))
    else:
        local = local.astimezone(ZoneInfo(timezone))
    if local.hour == MORNING_HOUR:
        return AlertSlot.MORNING
    if local.hour == EVENING_HOUR:
        return AlertSlot.EVENING
    return None


def due_windows_today(kind: EventKind, due: date, today: date) -> list[ReminderWindow]:
    """Return one-shot reminder windows that fire for this event on `today`."""
    matched: list[ReminderWindow] = []
    for window, days_before in windows_for_kind(kind):
        if today == due - timedelta(days=days_before):
            matched.append(window)
    return matched


def workflow_nags_today(
    issue: JiraCalendarIssue,
    today: date,
    *,
    slot: Optional[AlertSlot],
) -> list[ReminderWindow]:
    """Status-based nags for holiday/promo. Birthdays: none."""
    if not issue.kind.is_actionable:
        return []
    if issue.status_category is StatusCategory.DONE:
        return []

    days = days_until_due(issue.due_date, today)
    nags: list[ReminderWindow] = []

    # Start-work: still To Do, within T-30 .. T-1
    if (
        issue.status_category is StatusCategory.NEW
        and 1 <= days <= START_WORK_MAX_DAYS
        and slot is not None
    ):
        if slot is AlertSlot.MORNING:
            nags.append(ReminderWindow.NAG_START_WORK_MORNING)
        elif slot is AlertSlot.EVENING:
            nags.append(ReminderWindow.NAG_START_WORK_EVENING)

    # Finish-done: not Done yet, within T-5 .. T-1, morning only
    if (
        1 <= days <= FINISH_DONE_MAX_DAYS
        and slot is AlertSlot.MORNING
    ):
        nags.append(ReminderWindow.NAG_FINISH_DONE_MORNING)

    return nags


def evaluate_issue(
    issue: JiraCalendarIssue,
    today: date,
    *,
    slot: Optional[AlertSlot] = None,
) -> list[ReminderWindow]:
    """One-shot date windows + slot-dependent workflow nags."""
    windows = due_windows_today(issue.kind, issue.due_date, today)
    windows.extend(workflow_nags_today(issue, today, slot=slot))
    # Deduplicate while preserving order
    seen: set[ReminderWindow] = set()
    out: list[ReminderWindow] = []
    for w in windows:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def idempotency_key(
    issue_key: str,
    window: ReminderWindow,
    due: date,
    *,
    today: Optional[date] = None,
) -> str:
    """One-shot windows: per due date. Nags: per calendar day (+ slot in window name)."""
    if window.value.startswith("nag_"):
        day = (today or date.today()).isoformat()
        return f"{issue_key}|{window.value}|{due.isoformat()}|{day}"
    return f"{issue_key}|{window.value}|{due.isoformat()}"
