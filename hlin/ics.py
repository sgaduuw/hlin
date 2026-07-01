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


class InvalidICS(ValueError):
    """The upload could not be read as a calendar with at least one usable event."""


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
    ``InvalidICS`` on anything that is not a readable calendar event, malformed
    bytes, no VEVENT, or a VEVENT we cannot turn into fields (e.g. a duplicate
    property, which icalendar surfaces as a list), so the route returns a
    friendly 400 rather than a 500. The whole parse is guarded for that reason.
    """
    try:
        events = list(Calendar.from_ical(data).walk("VEVENT"))
        if not events:
            raise InvalidICS("No event (VEVENT) was found in the file.")
        vevent = events[0]
        event = ParsedEvent(
            kind_suggestion=_kind(vevent.get("summary")),
            scheduled_at=_start(vevent.get("dtstart")),
            notes=_notes(vevent.get("location"), vevent.get("description")),
        )
    except InvalidICS:
        raise  # keep the specific "no event" message
    except Exception as exc:  # malformed bytes, duplicate props, odd value types
        raise InvalidICS("Could not read a calendar event from this file.") from exc
    return event, len(events)


def _kind(summary) -> str | None:
    # SUMMARY is free text and can be long; cap it, the user refines the kind.
    if summary is None:
        return None
    return str(summary).strip()[:40] or None


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
