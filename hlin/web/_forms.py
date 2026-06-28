"""Small form-field parsers shared by the write routes.

HTML date / datetime-local inputs arrive as ISO strings (or empty); these
turn them into ``date`` / ``datetime`` or ``None``.
"""

from __future__ import annotations

from datetime import date, datetime


def parse_date(raw: str | None) -> date | None:
    raw = (raw or "").strip()
    return date.fromisoformat(raw) if raw else None


def parse_datetime(raw: str | None) -> datetime | None:
    raw = (raw or "").strip()
    return datetime.fromisoformat(raw) if raw else None
