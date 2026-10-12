"""Assignments from every class, filtered by how soon they are due."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from assistant.classes import course_title, list_assignments

WINDOWS = (1, 7, 30, 90)
_NO_DATE = {"", "unknown", "none", "n/a", "tbd"}
_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m-%d-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%B %d",
    "%b %d",
)


@dataclass(frozen=True)
class TodoItem:
    class_folder: str
    class_title: str
    slug: str
    title: str
    due_text: str
    due: date | None

    def days_until(self, today: date) -> int | None:
        if self.due is None:
            return None
        return (self.due - today).days


def parse_due(text: str, today: date) -> date | None:
    """Read a calendar date. Weekday names and 'unknown' stay undated."""
    raw = " ".join(text.replace(",", ", ").split())
    raw = raw.strip().strip(".")
    if raw.lower() in _NO_DATE:
        return None
    for fmt in _FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt and "%y" not in fmt:
            parsed = parsed.replace(year=today.year)
            if parsed < today - timedelta(days=180):
                parsed = parsed.replace(year=today.year + 1)
        return parsed
    return None


def collect_todos(root: Path, today: date) -> list[TodoItem]:
    if not root.is_dir():
        return []
    items: list[TodoItem] = []
    for course in sorted((path for path in root.iterdir() if path.is_dir() and not path.is_symlink()), key=lambda path: path.name):
        for assignment in list_assignments(root, course.name):
            due_text = assignment["due"]
            items.append(
                TodoItem(
                    class_folder=course.name,
                    class_title=course_title(course),
                    slug=assignment["slug"],
                    title=assignment["title"],
                    due_text=due_text,
                    due=parse_due(due_text, today),
                )
            )
    items.sort(key=lambda item: (item.due is None, item.due or date.max, item.title.lower()))
    return items


def filter_todos(items: list[TodoItem], today: date, days: int | None) -> list[TodoItem]:
    """Keep assignments due within the next `days`, including anything overdue."""
    if days is None:
        return items
    kept: list[TodoItem] = []
    for item in items:
        remaining = item.days_until(today)
        if remaining is not None and remaining <= days:
            kept.append(item)
    return kept


def due_phrase(item: TodoItem, today: date) -> str:
    remaining = item.days_until(today)
    if remaining is None:
        return "No due date"
    if remaining < -1:
        return f"Overdue by {-remaining} days"
    if remaining == -1:
        return "Overdue by 1 day"
    if remaining == 0:
        return "Due today"
    if remaining == 1:
        return "Due tomorrow"
    return f"Due in {remaining} days"
