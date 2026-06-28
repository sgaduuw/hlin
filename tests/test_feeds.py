"""iCalendar feed tests: all-day vs timed events, stable UIDs, birthdays.

Uses the in-memory session fixture to build real loaded objects, then
inspects the generated VEVENTs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from hlin import feeds
from hlin.models import (
    Appointment,
    AppointmentStatus,
    Contact,
    ContactKind,
    Person,
    RecurringObligation,
    Role,
)

TODAY = date(2026, 6, 28)


def _child(session, name="Alice") -> Person:
    person = Person(name=name, role=Role.CHILD)
    session.add(person)
    session.flush()
    return person


def _events(cal):
    return list(cal.walk("VEVENT"))


def test_obligation_renders_all_day_event(session):
    person = _child(session)
    obligation = RecurringObligation(
        person_id=person.id, kind="tandarts", interval_months=6, last_done=date(2026, 1, 1)
    )
    session.add(obligation)
    session.commit()
    session.refresh(person)

    events = _events(feeds.person_calendar(person, today=TODAY))
    assert len(events) == 1
    event = events[0]
    assert str(event["uid"]) == f"obligation-{obligation.id}-due@hlin"
    assert event.decoded("dtstart") == date(2026, 7, 1)  # a date -> all-day
    assert "tandarts due" in str(event["summary"])


def test_booked_appointment_renders_timed_event(session):
    person = _child(session)
    when = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
    appointment = Appointment(
        person_id=person.id, kind="huisarts", status=AppointmentStatus.BOOKED, scheduled_at=when
    )
    session.add(appointment)
    session.commit()
    session.refresh(person)

    events = _events(feeds.person_calendar(person, today=TODAY))
    assert len(events) == 1
    event = events[0]
    assert str(event["uid"]) == f"appointment-{appointment.id}@hlin"
    assert event.decoded("dtstart") == when  # a datetime -> timed


def test_unbooked_appointment_is_excluded(session):
    person = _child(session)
    appointment = Appointment(
        person_id=person.id,
        kind="huisarts",
        status=AppointmentStatus.DUE,
        scheduled_at=datetime(2026, 7, 10, 9, 30, tzinfo=UTC),
    )
    session.add(appointment)
    session.commit()
    session.refresh(person)

    assert _events(feeds.person_calendar(person, today=TODAY)) == []


def test_birthday_is_yearly_recurring_all_day(session):
    contact = Contact(name="Robin", kind=ContactKind.FRIEND, birthday=date(2016, 3, 3))
    session.add(contact)
    session.commit()

    cal = feeds.social_calendar([contact])
    events = _events(cal)
    assert len(events) == 1
    assert str(events[0]["uid"]) == f"birthday-{contact.id}@hlin"
    # Assert on the wire format the calendar client actually sees: an all-day
    # (VALUE=DATE) event recurring yearly.
    ics = feeds.to_ics(cal).decode()
    assert "DTSTART;VALUE=DATE:20160303" in ics
    assert "RRULE:FREQ=YEARLY" in ics


def test_contact_without_birthday_is_skipped(session):
    contact = Contact(name="No Birthday", kind=ContactKind.FRIEND, birthday=None)
    session.add(contact)
    session.commit()
    assert _events(feeds.social_calendar([contact])) == []


def test_obligation_uid_is_stable_across_today(session):
    """The UID must not depend on today, or clients would duplicate events."""
    person = _child(session)
    obligation = RecurringObligation(
        person_id=person.id, kind="tandarts", interval_months=6, last_done=date(2026, 1, 1)
    )
    session.add(obligation)
    session.commit()
    session.refresh(person)

    uid_now = str(_events(feeds.person_calendar(person, today=TODAY))[0]["uid"])
    uid_later = str(_events(feeds.person_calendar(person, today=date(2027, 1, 1)))[0]["uid"])
    assert uid_now == uid_later


def test_combined_feed_spans_all_persons(session):
    alice = _child(session, "Alice")
    bob = _child(session, "Bob")
    for person in (alice, bob):
        session.add(
            RecurringObligation(
                person_id=person.id, kind="tandarts", interval_months=6, last_done=date(2026, 1, 1)
            )
        )
    session.commit()

    events = _events(feeds.combined_calendar([alice, bob], today=TODAY))
    summaries = {str(e["summary"]) for e in events}
    assert summaries == {"Alice tandarts due", "Bob tandarts due"}
