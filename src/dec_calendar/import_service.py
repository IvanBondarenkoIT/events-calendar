from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from dec_calendar.config import REPO_ROOT, Settings
from dec_calendar.jira_client import JiraClient, text_to_adf
from dec_calendar.models import CalendarEventDraft, EventKind
from dec_calendar.parsers.birthdays import parse_birthdays_file
from dec_calendar.parsers.excel_events import (
    find_excel_workbook,
    holiday_checklist,
    merge_unique_by_summary,
    parse_excel_calendar,
)

logger = logging.getLogger(__name__)

BATUMI_SUMMARY = "[Промо] День рождения Dim Kava Batumi"


@dataclass
class ImportResult:
    created: list[str]
    skipped_existing: list[str]
    failed: list[tuple[str, str]]
    updated: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.created) + len(self.updated)


def pilot_drafts() -> list[CalendarEventDraft]:
    """Agreed pilot events (may overlap Excel — import is idempotent by summary)."""
    autumn = CalendarEventDraft(
        summary="[Промо] Начало осени",
        kind=EventKind.PROMO,
        due_date=date(2026, 9, 1),
        description=holiday_checklist("Начало осени")
        + "\nПилот: тестовое событие (label pilot-test).",
        extra_labels=("seasonal", "pilot-test"),
        source="pilot",
    )
    school = CalendarEventDraft(
        summary="[Праздник] Начало учебного года",
        kind=EventKind.HOLIDAY,
        due_date=date(2026, 9, 15),
        description=holiday_checklist("Начало учебного года")
        + "\nРеальное событие пилота (Грузия / сезон).",
        extra_labels=("georgia", "seasonal"),
        source="pilot",
    )
    return [autumn, school]


def extra_events_drafts() -> list[CalendarEventDraft]:
    """Manual DK extras — order is intentional (create/update in this sequence)."""
    return [
        CalendarEventDraft(
            summary="[Промо] День машины (эспрессо-способ)",
            kind=EventKind.PROMO,
            due_date=date(2026, 9, 5),
            description=holiday_checklist("День машины (эспрессо-способ)")
            + "\nКофейный инфоповод: день эспрессо-машины / эспрессо-способа.",
            extra_labels=("coffee",),
            source="manual:extra",
        ),
        CalendarEventDraft(
            summary="[Промо] День рождения Dim Kava Georgia",
            kind=EventKind.PROMO,
            due_date=date(2027, 4, 29),
            description=holiday_checklist("День рождения Dim Kava Georgia")
            + "\nОснование компании: 29.04.2014. Ежегодный DK-повод (не ДР сотрудника).",
            extra_labels=("dk-internal", "georgia"),
            source="manual:extra",
        ),
        CalendarEventDraft(
            summary="[Промо] День рождения Дім Кави Україна",
            kind=EventKind.PROMO,
            due_date=date(2027, 5, 20),
            description=holiday_checklist("День рождения Дім Кави Україна")
            + "\nОснование: 20.05.1995. Ежегодный DK-повод (не ДР сотрудника).",
            extra_labels=("dk-internal",),
            source="manual:extra",
        ),
        CalendarEventDraft(
            summary="[Праздник] День защиты детей",
            kind=EventKind.HOLIDAY,
            due_date=date(2027, 6, 1),
            description=holiday_checklist("День защиты детей")
            + "\nМеждународный день защиты детей (1 июня).",
            extra_labels=("international",),
            source="manual:extra",
        ),
        CalendarEventDraft(
            summary="[Промо] День рождения DK Paliashvili 66",
            kind=EventKind.PROMO,
            due_date=date(2027, 7, 12),
            description=holiday_checklist("День рождения DK Paliashvili 66")
            + "\nОткрытие точки: 12.07.2016. Ежегодный DK-повод (не ДР сотрудника).",
            extra_labels=("dk-internal",),
            source="manual:extra",
        ),
        CalendarEventDraft(
            summary=BATUMI_SUMMARY,
            kind=EventKind.PROMO,
            due_date=date(2027, 8, 9),
            description=holiday_checklist("День рождения Dim Kava Batumi")
            + "\nДата точки: 09.08 (исправлено с 10.08). Ежегодный DK-повод.",
            extra_labels=("dk-internal",),
            source="manual:extra",
        ),
    ]


def sort_drafts_chronologically(drafts: list[CalendarEventDraft]) -> list[CalendarEventDraft]:
    """Order: dated ascending (soonest first), then needs-date / no date at the end."""

    def key(d: CalendarEventDraft) -> tuple[int, date, str]:
        if d.due_date is None or d.needs_date:
            return (1, date.max, d.summary)
        return (0, d.due_date, d.summary)

    return sorted(drafts, key=key)


def build_import_drafts(
    *,
    repo_root: Path = REPO_ROOT,
    today: Optional[date] = None,
    include_excel: bool = True,
    include_birthdays: bool = True,
    include_pilot: bool = True,
    include_extra: bool = True,
) -> list[CalendarEventDraft]:
    today = today or date.today()
    drafts: list[CalendarEventDraft] = []

    if include_excel:
        xlsx = find_excel_workbook(repo_root)
        drafts.extend(parse_excel_calendar(xlsx))
        logger.info("Excel drafts from %s: %s", xlsx.name, len(drafts))

    if include_birthdays:
        nini = repo_root / "Nini calendar TG.txt"
        bday = parse_birthdays_file(nini, today=today)
        drafts.extend(bday)
        logger.info("Birthday drafts: %s", len(bday))

    if include_pilot:
        drafts.extend(pilot_drafts())

    if include_extra:
        # After Excel so merge last-wins applies correct Batumi 09.08 over Excel 10.08.
        drafts.extend(extra_events_drafts())

    return sort_drafts_chronologically(merge_unique_by_summary(drafts))


def delete_all_calendar_issues(client: JiraClient, *, dry_run: bool = False) -> list[str]:
    """Remove all DEC calendar-labeled issues (for clean chronological re-import)."""
    issues = client.list_importable_issues()
    # Delete highest keys first to reduce mid-list churn in UI.
    keys = sorted(
        (i["key"] for i in issues if i.get("key")),
        key=lambda k: int(k.split("-")[1]),
        reverse=True,
    )
    deleted: list[str] = []
    for key in keys:
        if dry_run:
            logger.info("[dry-run] would delete %s", key)
            deleted.append(key)
            continue
        client.delete_issue(key)
        deleted.append(key)
    return deleted


def import_drafts_to_jira(
    client: JiraClient,
    drafts: list[CalendarEventDraft],
    *,
    dry_run: bool = False,
    preserve_order: bool = False,
    update_existing: bool = False,
) -> ImportResult:
    created: list[str] = []
    skipped: list[str] = []
    updated: list[str] = []
    failed: list[tuple[str, str]] = []

    if not preserve_order:
        drafts = sort_drafts_chronologically(drafts)

    existing_cache: list = []
    if not dry_run:
        existing_cache = client.list_importable_issues()

    for draft in drafts:
        try:
            if not dry_run:
                existing = client.find_by_summary(draft.summary, cache=existing_cache)
                if existing:
                    key = existing.get("key") or draft.summary
                    if update_existing:
                        fields: dict = {
                            "description": text_to_adf(draft.description),
                            "labels": draft.labels,
                        }
                        if draft.due_date is not None and not draft.needs_date:
                            fields["duedate"] = draft.due_date.isoformat()
                        client.update_issue_fields(key, fields)
                        updated.append(key)
                        logger.info("Updated %s — %s", key, draft.summary)
                    else:
                        skipped.append(key)
                        logger.info("Skip existing: %s (%s)", draft.summary, key)
                    continue
            if dry_run:
                created.append(f"DRY:{draft.summary}")
                logger.info("[dry-run] would create: %s", draft.summary)
                continue
            result = client.create_issue_from_draft(draft)
            key = result.get("key") or "?"
            created.append(key)
            existing_cache.append(
                {"key": key, "fields": {"summary": draft.summary, "labels": draft.labels}}
            )
            logger.info("Created %s — %s", key, draft.summary)
        except Exception as exc:  # noqa: BLE001 — collect per-row failures
            logger.exception("Failed to import %s", draft.summary)
            failed.append((draft.summary, str(exc)))

    return ImportResult(
        created=created,
        skipped_existing=skipped,
        failed=failed,
        updated=updated,
    )


def run_import(
    settings: Settings,
    *,
    dry_run: bool = False,
    today: Optional[date] = None,
    replace: bool = False,
) -> ImportResult:
    drafts = build_import_drafts(today=today)
    client = JiraClient(settings)
    if replace:
        removed = delete_all_calendar_issues(client, dry_run=dry_run)
        logger.info("Replace: removed %s existing calendar issues", len(removed))
    return import_drafts_to_jira(client, drafts, dry_run=dry_run)


def run_import_extra(
    settings: Settings,
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Create/update manual extras in listed order (no chronological sort)."""
    drafts = extra_events_drafts()
    client = JiraClient(settings)
    return import_drafts_to_jira(
        client,
        drafts,
        dry_run=dry_run,
        preserve_order=True,
        update_existing=True,
    )
