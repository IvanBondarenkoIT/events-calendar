from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from dec_calendar.idempotency import IdempotencyStore
from dec_calendar.messages import format_alert_message
from dec_calendar.models import AlertSlot, EventKind, JiraCalendarIssue, ReminderWindow, StatusCategory
from dec_calendar.parsers.birthdays import next_occurrence, parse_birthday_lines, parse_birthdays_file
from dec_calendar.parsers.excel_events import find_excel_workbook, parse_excel_calendar
from dec_calendar.reminders import due_windows_today, evaluate_issue, idempotency_key, resolve_slot
from dec_calendar.config import REPO_ROOT


def _issue(
    kind: EventKind,
    due: date,
    summary: str = "Test",
    *,
    status_category: StatusCategory = StatusCategory.NEW,
    status_name: str = "К выполнению",
) -> JiraCalendarIssue:
    return JiraCalendarIssue(
        key="DEC-1",
        summary=summary,
        kind=kind,
        due_date=due,
        labels=(kind.jira_label,),
        browse_url="https://example.atlassian.net/browse/DEC-1",
        status_name=status_name,
        status_category=status_category,
    )


class TestReminderWindows:
    def test_holiday_t30_and_t15(self) -> None:
        due = date(2026, 9, 15)
        assert due_windows_today(EventKind.HOLIDAY, due, date(2026, 8, 16)) == [
            ReminderWindow.T_MINUS_30
        ]
        assert due_windows_today(EventKind.PROMO, due, date(2026, 8, 31)) == [
            ReminderWindow.T_MINUS_15
        ]
        assert due_windows_today(EventKind.HOLIDAY, due, date(2026, 9, 1)) == []

    def test_birthday_t1_and_t0(self) -> None:
        due = date(2026, 9, 26)
        assert due_windows_today(EventKind.BIRTHDAY, due, date(2026, 9, 25)) == [
            ReminderWindow.T_MINUS_1
        ]
        assert due_windows_today(EventKind.BIRTHDAY, due, date(2026, 9, 26)) == [
            ReminderWindow.T_MINUS_0
        ]
        # Birthdays must NOT get holiday windows
        assert due_windows_today(EventKind.BIRTHDAY, due, date(2026, 8, 27)) == []

    def test_evaluate_issue(self) -> None:
        issue = _issue(EventKind.PROMO, date(2026, 9, 1), "[Промо] Начало осени")
        assert evaluate_issue(issue, date(2026, 8, 17)) == [ReminderWindow.T_MINUS_15]

    def test_idempotency_key_includes_due(self) -> None:
        k1 = idempotency_key("DEC-1", ReminderWindow.T_MINUS_0, date(2026, 1, 2))
        k2 = idempotency_key("DEC-1", ReminderWindow.T_MINUS_0, date(2027, 1, 2))
        assert k1 != k2


class TestWorkflowNags:
    def test_start_work_while_todo_morning_and_evening(self) -> None:
        issue = _issue(EventKind.HOLIDAY, date(2026, 9, 15))
        today = date(2026, 8, 27)  # 19 days before
        morning = evaluate_issue(issue, today, slot=AlertSlot.MORNING)
        evening = evaluate_issue(issue, today, slot=AlertSlot.EVENING)
        assert ReminderWindow.NAG_START_WORK_MORNING in morning
        assert ReminderWindow.NAG_START_WORK_EVENING in evening
        assert ReminderWindow.NAG_FINISH_DONE_MORNING not in morning  # > 5 days

    def test_no_start_work_when_in_progress(self) -> None:
        issue = _issue(
            EventKind.PROMO,
            date(2026, 9, 15),
            status_category=StatusCategory.INDETERMINATE,
            status_name="В работе",
        )
        windows = evaluate_issue(issue, date(2026, 8, 27), slot=AlertSlot.MORNING)
        assert ReminderWindow.NAG_START_WORK_MORNING not in windows

    def test_finish_done_within_five_days_morning(self) -> None:
        issue = _issue(
            EventKind.HOLIDAY,
            date(2026, 9, 15),
            status_category=StatusCategory.INDETERMINATE,
            status_name="В работе",
        )
        today = date(2026, 9, 10)  # 5 days before
        windows = evaluate_issue(issue, today, slot=AlertSlot.MORNING)
        assert ReminderWindow.NAG_FINISH_DONE_MORNING in windows
        evening = evaluate_issue(issue, today, slot=AlertSlot.EVENING)
        assert ReminderWindow.NAG_FINISH_DONE_MORNING not in evening

    def test_birthday_no_workflow_nags(self) -> None:
        issue = _issue(EventKind.BIRTHDAY, date(2026, 9, 5))
        windows = evaluate_issue(issue, date(2026, 9, 1), slot=AlertSlot.MORNING)
        assert ReminderWindow.NAG_START_WORK_MORNING not in windows
        assert ReminderWindow.NAG_FINISH_DONE_MORNING not in windows

    def test_nag_idempotency_includes_day(self) -> None:
        k1 = idempotency_key(
            "DEC-1",
            ReminderWindow.NAG_START_WORK_MORNING,
            date(2026, 9, 15),
            today=date(2026, 8, 27),
        )
        k2 = idempotency_key(
            "DEC-1",
            ReminderWindow.NAG_START_WORK_MORNING,
            date(2026, 9, 15),
            today=date(2026, 8, 28),
        )
        assert k1 != k2

    def test_resolve_slot_auto(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = "Asia/Tbilisi"
        morning = datetime(2026, 8, 27, 10, 5, tzinfo=ZoneInfo(tz))
        evening = datetime(2026, 8, 27, 22, 0, tzinfo=ZoneInfo(tz))
        noon = datetime(2026, 8, 27, 12, 0, tzinfo=ZoneInfo(tz))
        assert resolve_slot(AlertSlot.AUTO, timezone=tz, now=morning) is AlertSlot.MORNING
        assert resolve_slot(AlertSlot.AUTO, timezone=tz, now=evening) is AlertSlot.EVENING
        assert resolve_slot(AlertSlot.AUTO, timezone=tz, now=noon) is None


class TestMessages:
    def test_holiday_message_contains_jira_link(self) -> None:
        issue = _issue(EventKind.HOLIDAY, date(2026, 9, 15), "[Праздник] Начало учебного года")
        text = format_alert_message(issue, ReminderWindow.T_MINUS_30)
        assert "30" in text
        assert "DEC-1" in text
        assert "учебного" in text

    def test_birthday_strips_prefix(self) -> None:
        issue = _issue(EventKind.BIRTHDAY, date(2026, 9, 26), "[ДР] Аня Батуми")
        assert format_alert_message(issue, ReminderWindow.T_MINUS_1) == (
            "🎂 Завтра день рождения: Аня Батуми"
        )
        assert format_alert_message(issue, ReminderWindow.T_MINUS_0) == (
            "🎂 Сегодня день рождения: Аня Батуми"
        )


class TestBirthdays:
    def test_next_occurrence_rolls_year(self) -> None:
        assert next_occurrence(1, 2, today=date(2026, 8, 21)) == date(2027, 1, 2)
        assert next_occurrence(9, 26, today=date(2026, 8, 21)) == date(2026, 9, 26)

    def test_parse_nini_file(self) -> None:
        path = REPO_ROOT / "Nini calendar TG.txt"
        drafts = parse_birthdays_file(path, today=date(2026, 8, 21))
        assert len(drafts) >= 20
        names = {d.summary for d in drafts}
        assert "[ДР] Аня Батуми" in names
        assert "[ДР] Равиль" in names
        # Should not treat holidays as birthdays
        assert not any("Новый год" in d.summary for d in drafts)

    def test_parse_line_variants(self) -> None:
        text = "Саша - 2 Февраля\nМишка - 19 августа\n"
        drafts = parse_birthday_lines(text, today=date(2026, 1, 1))
        assert len(drafts) == 2
        assert drafts[0].due_date == date(2026, 2, 2)


class TestExcel:
    def test_parse_workbook(self) -> None:
        xlsx = find_excel_workbook(REPO_ROOT)
        drafts = parse_excel_calendar(xlsx)
        dated = [d for d in drafts if d.due_date]
        needs = [d for d in drafts if d.needs_date]
        assert len(dated) >= 25
        assert len(needs) >= 3
        autumn = next(d for d in dated if "Начало осени" in d.summary)
        assert autumn.due_date == date(2026, 9, 1)
        assert autumn.kind is EventKind.PROMO


class TestChronologicalSort:
    def test_build_import_ordered_by_due_date(self) -> None:
        from dec_calendar.import_service import build_import_drafts

        drafts = build_import_drafts(today=date(2026, 8, 27))
        dated = [d for d in drafts if d.due_date and not d.needs_date]
        dates = [d.due_date for d in dated]
        assert dates == sorted(dates)
        assert dated[0].due_date <= dated[-1].due_date
        needs = [d for d in drafts if d.needs_date]
        if needs and dated:
            assert drafts.index(needs[0]) > drafts.index(dated[-1])


class TestIdempotencyStore:
    def test_persist_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        store = IdempotencyStore.load(path)
        assert not store.has("a")
        store.add("a")
        store2 = IdempotencyStore.load(path)
        assert store2.has("a")
