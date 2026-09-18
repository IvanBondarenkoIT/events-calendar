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


def _settings(*, via_hub: bool, tmp_path: Path) -> "Settings":
    from dec_calendar.config import Settings

    return Settings(
        timezone="Asia/Tbilisi",
        jira_url="https://example.atlassian.net",
        jira_email="a@b.c",
        jira_api_token="t",
        jira_project_key="DEC",
        jira_issue_type="Task",
        jira_ssl_verify=True,
        telegram_bot_token="bot-token",
        telegram_chat_id="-100123",
        telegram_disable_ssl_verify=False,
        notify_hub_url="http://127.0.0.1:8080",
        notify_hub_api_key="hub-key",
        notify_via_hub=via_hub,
        dry_run=False,
        idempotency_path=tmp_path / "alert_state.json",
        log_level="INFO",
    )


class TestNotifyHubClient:
    def test_calendar_event_id_and_payload(self) -> None:
        from dec_calendar.notify_hub_client import build_calendar_event, calendar_event_id

        issue = _issue(EventKind.PROMO, date(2026, 9, 1), "[Промо] Начало осени")
        idem = "DEC-1|t_minus_15|2026-09-01"
        event = build_calendar_event(
            idem_key=idem,
            issue=issue,
            window=ReminderWindow.T_MINUS_15,
            body="hello",
            today=date(2026, 8, 17),
            slot=AlertSlot.MORNING,
            seed_chat_id="-100123",
        )
        assert event["event_id"] == calendar_event_id(idem)
        assert event["type"] == "calendar.event.v1"
        assert event["channels"] == ["public"]
        assert event["require_ack"] is False
        assert event["targets"]["chat_ids"] == [-100123]
        assert event["data"]["jira_key"] == "DEC-1"

        nag = build_calendar_event(
            idem_key="DEC-1|nag_start_work_morning|2026-09-01|2026-08-17",
            issue=issue,
            window=ReminderWindow.NAG_START_WORK_MORNING,
            body="nag",
            today=date(2026, 8, 17),
            slot=AlertSlot.MORNING,
            seed_chat_id="-100123",
        )
        assert nag["type"] == "calendar.reminder.v1"
        assert nag["channels"] == ["public"]

    def test_post_event_accepted_and_duplicate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dec_calendar.notify_hub_client import NotifyHubClient, NotifyHubError

        calls: list[dict] = []

        class FakeResp:
            def __init__(self, status_code: int, payload: dict) -> None:
                self.status_code = status_code
                self._payload = payload
                self.content = b"{}"
                self.text = str(payload)

            def json(self) -> dict:
                return self._payload

        def fake_post(url, json, headers, timeout):  # noqa: A002
            calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
            status = "duplicate" if len(calls) > 1 else "accepted"
            return FakeResp(200, {"status": status, "event_id": json["event_id"]})

        monkeypatch.setattr("dec_calendar.notify_hub_client.requests.post", fake_post)
        client = NotifyHubClient(_settings(via_hub=True, tmp_path=Path(".")))
        event = {"event_id": "calendar-x", "type": "calendar.event.v1"}
        first = client.post_event(event)
        second = client.post_event(event)
        assert first["status"] == "accepted"
        assert second["status"] == "duplicate"
        assert calls[0]["headers"]["X-Api-Key"] == "hub-key"
        assert calls[0]["url"].endswith("/v1/events")

        def boom(*_a, **_k):
            return FakeResp(500, {})

        monkeypatch.setattr("dec_calendar.notify_hub_client.requests.post", boom)
        with pytest.raises(NotifyHubError):
            client.post_event(event)


class TestJobCutover:
    def test_hub_xor_telegram(self, tmp_path: Path) -> None:
        from dec_calendar.job import run_reminder_job

        issue = _issue(EventKind.PROMO, date(2026, 9, 1), "[Промо] Начало осени")

        class FakeJira:
            def list_calendar_issues(self):
                return [issue]

            def add_comment(self, *_a, **_k):
                return None

        class FakeTelegram:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def send_message(self, text: str) -> None:
                self.sent.append(text)

        class FakeHub:
            def __init__(self) -> None:
                self.events: list[dict] = []

            def post_event(self, event: dict) -> dict:
                self.events.append(event)
                return {"status": "accepted", "event_id": event["event_id"]}

        telegram = FakeTelegram()
        hub = FakeHub()
        report = run_reminder_job(
            _settings(via_hub=True, tmp_path=tmp_path),
            today=date(2026, 8, 17),
            slot=AlertSlot.MORNING,
            jira=FakeJira(),  # type: ignore[arg-type]
            telegram=telegram,  # type: ignore[arg-type]
            notify_hub=hub,  # type: ignore[arg-type]
            comment_on_jira=False,
        )
        assert report.sent
        assert hub.events
        types = {e["type"] for e in hub.events}
        assert "calendar.event.v1" in types
        assert "calendar.reminder.v1" in types
        assert telegram.sent == []

        telegram2 = FakeTelegram()
        hub2 = FakeHub()
        report2 = run_reminder_job(
            _settings(via_hub=False, tmp_path=tmp_path / "tg"),
            today=date(2026, 8, 17),
            slot=AlertSlot.MORNING,
            jira=FakeJira(),  # type: ignore[arg-type]
            telegram=telegram2,  # type: ignore[arg-type]
            notify_hub=hub2,  # type: ignore[arg-type]
            comment_on_jira=False,
        )
        assert report2.sent
        assert telegram2.sent
        assert hub2.events == []

