from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from dec_calendar.models import CalendarEventDraft, EventKind

# "Равиль- 2 января" / "Линда Батуми - 20 января" / "Саша - 2 Февраля"
BIRTHDAY_LINE_RE = re.compile(
    r"^\s*(?P<name>.+?)\s*[-–—]\s*(?P<day>\d{1,2})\s+(?P<month>[А-Яа-яA-Za-z]+)\s*$"
)

# Telegram Desktop export header, e.g. "[20.08.2026 13:12] Nini … HR: Равиль- 2 января"
TG_HEADER_RE = re.compile(r"^\[\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\]\s*[^:]*:\s*(?P<body>.*)$")

MONTHS_RU = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def next_occurrence(month: int, day: int, *, today: date) -> date:
    """Next date for MM-DD on or after today (handles year rollover)."""
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        # Feb 29 in non-leap year → Feb 28
        if month == 2 and day == 29:
            candidate = date(today.year, 2, 28)
        else:
            raise
    if candidate < today:
        try:
            return date(today.year + 1, month, day)
        except ValueError:
            return date(today.year + 1, 2, 28)
    return candidate


def _strip_tg_header(line: str) -> str:
    m = TG_HEADER_RE.match(line)
    if m:
        return (m.group("body") or "").strip()
    return line.strip()


def _draft_from_match(name: str, day: int, month: int, *, today: date) -> CalendarEventDraft:
    due = next_occurrence(month, day, today=today)
    mmdd = f"{month:02d}-{day:02d}"
    return CalendarEventDraft(
        summary=f"[ДР] {name}",
        kind=EventKind.BIRTHDAY,
        due_date=due,
        description=(
            f"День рождения: {name}\n"
            f"birthday_mmdd: {mmdd}\n"
            "Оповещения: за день и в день (Telegram).\n"
            "Правки ФИО/даты — в этой карточке Jira."
        ),
        extra_labels=(),
        source="nini:birthdays",
        needs_date=False,
    )


def parse_birthday_lines(text: str, *, today: date) -> list[CalendarEventDraft]:
    drafts: list[CalendarEventDraft] = []
    for raw_line in text.splitlines():
        line = _strip_tg_header(raw_line)
        if not line:
            continue
        if "Главные государственные" in line or "религиозные" in line:
            continue
        m = BIRTHDAY_LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip().rstrip("-").strip()
        day = int(m.group("day"))
        month_name = m.group("month").strip().lower()
        month = MONTHS_RU.get(month_name)
        if month is None or not name:
            continue
        drafts.append(_draft_from_match(name, day, month, today=today))
    return drafts


def parse_birthdays_file(path: Path, *, today: date) -> list[CalendarEventDraft]:
    text = path.read_text(encoding="utf-8")
    return parse_birthday_lines(text, today=today)
