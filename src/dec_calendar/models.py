from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class EventKind(str, Enum):
    """Calendar event family — drives reminder windows."""

    HOLIDAY = "holiday"
    PROMO = "promo"
    BIRTHDAY = "birthday"

    @property
    def jira_label(self) -> str:
        return {
            EventKind.HOLIDAY: "calendar-holiday",
            EventKind.PROMO: "calendar-promo",
            EventKind.BIRTHDAY: "calendar-birthday",
        }[self]

    @classmethod
    def from_label(cls, label: str) -> Optional["EventKind"]:
        mapping = {
            "calendar-holiday": cls.HOLIDAY,
            "calendar-promo": cls.PROMO,
            "calendar-birthday": cls.BIRTHDAY,
        }
        return mapping.get(label)

    @classmethod
    def from_labels(cls, labels: list[str]) -> Optional["EventKind"]:
        for label in labels:
            kind = cls.from_label(label)
            if kind is not None:
                return kind
        return None

    @property
    def is_actionable(self) -> bool:
        """Holiday/promo need workflow nags; birthdays do not."""
        return self is not EventKind.BIRTHDAY


class StatusCategory(str, Enum):
    """Jira statusCategory.key values."""

    NEW = "new"  # To Do / К выполнению
    INDETERMINATE = "indeterminate"  # In Progress / В работе
    DONE = "done"


class ReminderWindow(str, Enum):
    T_MINUS_30 = "t_minus_30"
    T_MINUS_15 = "t_minus_15"
    T_MINUS_1 = "t_minus_1"
    T_MINUS_0 = "t_minus_0"
    NAG_START_WORK_MORNING = "nag_start_work_morning"
    NAG_START_WORK_EVENING = "nag_start_work_evening"
    NAG_FINISH_DONE_MORNING = "nag_finish_done_morning"


class AlertSlot(str, Enum):
    MORNING = "morning"
    EVENING = "evening"
    AUTO = "auto"


@dataclass(frozen=True)
class CalendarEventDraft:
    """Event ready to import into Jira (not yet an issue)."""

    summary: str
    kind: EventKind
    due_date: Optional[date]
    description: str
    extra_labels: tuple[str, ...] = ()
    source: str = ""
    needs_date: bool = False

    @property
    def labels(self) -> list[str]:
        labels = [self.kind.jira_label, *self.extra_labels]
        if self.needs_date:
            labels.append("needs-date")
        return labels


@dataclass(frozen=True)
class JiraCalendarIssue:
    """Normalized issue from Jira for reminder evaluation."""

    key: str
    summary: str
    kind: EventKind
    due_date: date
    labels: tuple[str, ...]
    browse_url: str
    status_name: str = ""
    status_category: StatusCategory = StatusCategory.NEW

    @property
    def is_todo(self) -> bool:
        return self.status_category is StatusCategory.NEW

    @property
    def is_in_progress(self) -> bool:
        return self.status_category is StatusCategory.INDETERMINATE

    @property
    def is_done(self) -> bool:
        return self.status_category is StatusCategory.DONE
