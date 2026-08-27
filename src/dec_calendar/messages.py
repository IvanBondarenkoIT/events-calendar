from __future__ import annotations

from datetime import date
from typing import Optional

from dec_calendar.models import EventKind, JiraCalendarIssue, ReminderWindow
from dec_calendar.reminders import days_until_due


def format_holiday_message(
    *,
    issue: JiraCalendarIssue,
    window: ReminderWindow,
) -> str:
    days = {
        ReminderWindow.T_MINUS_30: 30,
        ReminderWindow.T_MINUS_15: 15,
    }[window]
    urgency = (
        "Пора готовить акцию / ивент. Откройте карточку и пройдите чеклист."
        if days == 30
        else "Осталось две недели — проверьте чеклист подготовки."
    )
    return (
        f"📅 Через {days} дней: {issue.summary}\n"
        f"Дата: {issue.due_date.isoformat()}\n"
        f"Jira: {issue.browse_url}\n"
        f"\n{urgency}"
    )


def format_birthday_message(
    *,
    issue: JiraCalendarIssue,
    window: ReminderWindow,
) -> str:
    name = issue.summary
    for prefix in ("[ДР] ", "[Birthday] ", "[ДР]", "[Birthday]"):
        if name.startswith(prefix):
            name = name[len(prefix) :].strip()
            break
    if window is ReminderWindow.T_MINUS_1:
        return f"🎂 Завтра день рождения: {name}"
    if window is ReminderWindow.T_MINUS_0:
        return f"🎂 Сегодня день рождения: {name}"
    raise ValueError(f"Unsupported birthday window: {window}")


def format_start_work_nag(issue: JiraCalendarIssue, *, today: date) -> str:
    n = days_until_due(issue.due_date, today)
    status = issue.status_name or "К выполнению"
    return (
        f"⚠️ Событие через {n} дн. всё ещё в «{status}».\n"
        f"{issue.summary}\n"
        f"Дата: {issue.due_date.isoformat()}\n"
        f"Jira: {issue.browse_url}\n"
        f"\nПереведите карточку в «В работе», когда начнёте подготовку."
    )


def format_finish_done_nag(issue: JiraCalendarIssue, *, today: date) -> str:
    n = days_until_due(issue.due_date, today)
    return (
        f"🚨 До события {n} дн. — закройте подготовку.\n"
        f"{issue.summary}\n"
        f"Дата: {issue.due_date.isoformat()}\n"
        f"Статус: {issue.status_name or '?'}\n"
        f"Jira: {issue.browse_url}\n"
        f"\nДоведите чеклист и переведите карточку в «Готово» до даты события."
    )


def format_alert_message(
    issue: JiraCalendarIssue,
    window: ReminderWindow,
    *,
    today: Optional[date] = None,
) -> str:
    day = today or date.today()
    if window in (ReminderWindow.NAG_START_WORK_MORNING, ReminderWindow.NAG_START_WORK_EVENING):
        return format_start_work_nag(issue, today=day)
    if window is ReminderWindow.NAG_FINISH_DONE_MORNING:
        return format_finish_done_nag(issue, today=day)
    if issue.kind is EventKind.BIRTHDAY:
        return format_birthday_message(issue=issue, window=window)
    return format_holiday_message(issue=issue, window=window)


def jira_alert_comment(window: ReminderWindow, today: date) -> str:
    return f"[DEC calendar] Telegram alert sent for window `{window.value}` on {today.isoformat()}."
