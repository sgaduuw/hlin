"""Small form-field parsers shared by the write routes.

HTML date / datetime-local inputs arrive as ISO strings (or empty); these
turn them into ``date`` / ``datetime`` or ``None``. A malformed value (only
reachable from a crafted or odd client, since the native inputs submit ISO) is
treated as absent rather than raising, so a write route never 500s on a bad
date. ``enum_field`` is the analogue for `<select>` values.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from flask import abort


def parse_date(raw: str | None) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_datetime(raw: str | None) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def enum_field[E: enum.Enum](enum_cls: type[E], raw: str | None, *, default: E) -> E:
    """Coerce a form value to an enum member: blank -> ``default``, invalid ->
    HTTP 400. A crafted `<select>` value should not 500 the way ``EnumCls(bad)``
    would; this mirrors the validate-or-400 shape of ``views._form_role``."""
    raw = (raw or "").strip()
    if not raw:
        return default
    try:
        return enum_cls(raw)
    except ValueError:
        abort(400)
