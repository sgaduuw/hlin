"""Parse an uploaded .ics (iCalendar) invite into appointment fields.

One concern: turn the first ``VEVENT`` of an uploaded calendar into the fields
the review form pre-fills, using the ``icalendar`` library already present for
feed generation. Pure (bytes in, values out); the caller parses and discards
the raw file, nothing is stored. Malformed input raises ``InvalidICS`` so the
route can return a friendly 400 rather than a 500.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from icalendar import Calendar

# Cap the kind suggestion: SUMMARY is free text and can be long, while `kind` is
# a short vocabulary the user refines in the review form.
_KIND_SUGGESTION_MAX = 40


class InvalidICS(ValueError):
    """The upload is not a calendar with at least one event."""


@dataclass(frozen=True)
class ParsedEvent:
    """The fields lifted from a VEVENT, for pre-filling the review form."""

    kind_suggestion: str | None  # from SUMMARY (the user refines it)
    scheduled_at: datetime | None  # from DTSTART, as local wall time (naive)
    notes: str | None  # LOCATION + DESCRIPTION


def parse_invite(data: bytes) -> tuple[ParsedEvent, int]:
    """Parse the first ``VEVENT`` from ``data``.

    Returns ``(event, total_event_count)`` so the caller can note when a file
    holds more than one (invites are single-event in practice). Raises
    ``InvalidICS`` when the bytes are not a calendar with at least one event.
    """
    try:
        cal = Calendar.from_ical(data)
    except Exception as exc:  # icalendar raises assorted errors on malformed input
        raise InvalidICS("This does not look like a valid iCalendar (.ics) file.") from exc
    events = list(cal.walk("VEVENT"))
    if not events:
        raise InvalidICS("No event (VEVENT) was found in the file.")
    return _to_parsed(events[0]), len(events)


def _to_parsed(vevent) -> ParsedEvent:
    return ParsedEvent(
        kind_suggestion=_kind(vevent.get("summary")),
        scheduled_at=_start(vevent.get("dtstart")),
        notes=_notes(vevent.get("location"), vevent.get("description")),
    )


def _kind(summary) -> str | None:
    if summary is None:
        return None
    text = str(summary).strip()
    return text[:_KIND_SUGGESTION_MAX] or None


def _start(dtstart) -> datetime | None:
    """DTSTART as a naive local datetime, ready for a datetime-local input.

    An all-day event (DATE) has no time, so it becomes midnight. A timed event
    with a timezone is converted to local wall time (the container runs with the
    household TZ); a floating time is taken as-is. The user reviews it either way.
    """
    if dtstart is None:
        return None
    value = dtstart.dt
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone()  # to the system/local tz
        return value.replace(tzinfo=None)
    if isinstance(value, date):  # all-day event -> date only
        return datetime(value.year, value.month, value.day)
    return None


def _notes(location, description) -> str | None:
    parts = [str(p).strip() for p in (location, description) if p is not None and str(p).strip()]
    return "\n\n".join(parts) or None
