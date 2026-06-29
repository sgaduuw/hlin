"""iCalendar feed generation.

Read-only ``.ics`` feeds for the household's existing CalDAV clients. Three
event sources:

* booked appointments -> timed VEVENTs
* active obligations  -> all-day VEVENTs on the derived next-due date
* contact birthdays   -> yearly-recurring all-day VEVENTs

UIDs are stable (keyed on the row id, independent of ``today``) so
subscribing clients update events in place instead of duplicating them on
each refresh. The builders are pure (data in, ``Calendar`` out); the routes
in ``web/feeds.py`` supply the session-loaded objects and ``today``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from icalendar import Calendar, Event

from .models import Appointment, AppointmentStatus, Contact, Person
from .recall import next_due_date

_PRODID = "-//hlin//household tracker//EN"
_DOMAIN = "hlin"


def _calendar(name: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", _PRODID)
    cal.add("version", "2.0")
    cal.add("x-wr-calname", name)
    return cal


def _event(uid: str, summary: str) -> Event:
    event = Event()
    event.add("uid", uid)
    event.add("dtstamp", datetime.now(UTC))  # RFC 5545 requires DTSTAMP in a VEVENT
    event.add("summary", summary)
    return event


def _appointment_event(appointment: Appointment, person_name: str) -> Event:
    # Who/what/when only. The outcome is sensitive (redacted for anonymous
    # viewers in the web UI) and these feeds are anonymous-readable, so it must
    # never reach the event body. A booked appointment can still carry an
    # outcome if its status was edited back from done, hence no exception here.
    event = _event(f"appointment-{appointment.id}@{_DOMAIN}", f"{person_name} {appointment.kind}")
    event.add("dtstart", appointment.scheduled_at)  # datetime -> timed VEVENT
    event.add("dtend", appointment.scheduled_at + timedelta(hours=1))
    return event


def _obligation_event(person_name: str, kind: str, uid_id: int, due: date) -> Event:
    event = _event(f"obligation-{uid_id}-due@{_DOMAIN}", f"{person_name} {kind} due")
    event.add("dtstart", due)  # date -> all-day VEVENT
    event.add("dtend", due + timedelta(days=1))
    return event


def _birthday_event(contact: Contact) -> Event:
    event = _event(f"birthday-{contact.id}@{_DOMAIN}", f"{contact.name} birthday")
    event.add("dtstart", contact.birthday)  # date -> all-day VEVENT
    event.add("dtend", contact.birthday + timedelta(days=1))
    event.add("rrule", {"freq": "yearly"})
    return event


def _add_person_events(cal: Calendar, person: Person, *, today: date) -> None:
    for appointment in person.appointments:
        if appointment.status == AppointmentStatus.BOOKED and appointment.scheduled_at is not None:
            cal.add_component(_appointment_event(appointment, person.name))
    for obligation in person.obligations:
        if obligation.active:
            due = next_due_date(obligation, today=today)
            cal.add_component(_obligation_event(person.name, obligation.kind, obligation.id, due))


def person_calendar(person: Person, *, today: date) -> Calendar:
    cal = _calendar(f"hlin: {person.name}")
    _add_person_events(cal, person, today=today)
    return cal


def combined_calendar(persons: Iterable[Person], *, today: date) -> Calendar:
    cal = _calendar("hlin: all")
    for person in persons:
        _add_person_events(cal, person, today=today)
    return cal


def social_calendar(contacts: Iterable[Contact]) -> Calendar:
    cal = _calendar("hlin: birthdays")
    for contact in contacts:
        if contact.birthday is not None:
            cal.add_component(_birthday_event(contact))
    return cal


def to_ics(cal: Calendar) -> bytes:
    return cal.to_ical()
