"""Write-layer tests, with emphasis on the mark-done -> obligation cascade.

That cascade is the spec's "marking an appointment done advances the
matching obligation" behaviour and is correctness-critical, so it gets the
most cases (advance, never-backwards, kind mismatch, explicit done date).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from hlin import commands
from hlin.models import AppointmentStatus, ContactKind, Person, Role


def _person(session, name="Alice", role=Role.CHILD) -> Person:
    person = Person(name=name, role=role)
    session.add(person)
    session.flush()
    return person


def _booked(session, person_id, kind, when=datetime(2026, 6, 1, 9, 0, tzinfo=UTC)):
    return commands.add_appointment(
        session, person_id, kind=kind, status=AppointmentStatus.BOOKED, scheduled_at=when
    )


def test_add_appointment_defaults_to_due(session):
    person = _person(session)
    appointment = commands.add_appointment(session, person.id, kind="huisarts")
    session.commit()
    assert appointment.id is not None
    assert appointment.status == AppointmentStatus.DUE
    assert appointment.kind == "huisarts"


def test_add_obligation_is_active(session):
    person = _person(session)
    obligation = commands.add_obligation(
        session, person.id, kind="tandarts", interval_months=6, last_done=date(2026, 1, 1)
    )
    session.commit()
    assert obligation.active is True
    assert obligation.last_done == date(2026, 1, 1)


def test_log_outcome_marks_done_and_records(session):
    person = _person(session)
    appointment = _booked(session, person.id, "huisarts")
    session.commit()
    commands.log_appointment_outcome(
        session, appointment, outcome="all good", next_action="rebook in 3m"
    )
    session.commit()
    assert appointment.status == AppointmentStatus.DONE
    assert appointment.outcome == "all good"
    assert appointment.next_action == "rebook in 3m"


def test_log_outcome_advances_matching_obligation(session):
    person = _person(session)
    obligation = commands.add_obligation(
        session, person.id, kind="tandarts", interval_months=6, last_done=date(2025, 1, 1)
    )
    appointment = _booked(session, person.id, "tandarts")
    session.commit()
    commands.log_appointment_outcome(session, appointment, outcome=None, next_action=None)
    session.commit()
    assert obligation.last_done == date(2026, 6, 1)  # advanced to the appointment date


def test_log_outcome_never_moves_obligation_backwards(session):
    person = _person(session)
    obligation = commands.add_obligation(
        session, person.id, kind="tandarts", interval_months=6, last_done=date(2026, 12, 1)
    )
    appointment = _booked(session, person.id, "tandarts")  # older than last_done
    session.commit()
    commands.log_appointment_outcome(session, appointment, outcome=None, next_action=None)
    session.commit()
    assert obligation.last_done == date(2026, 12, 1)  # unchanged


def test_log_outcome_ignores_obligation_of_other_kind(session):
    person = _person(session)
    obligation = commands.add_obligation(
        session, person.id, kind="tandarts", interval_months=6, last_done=date(2025, 1, 1)
    )
    appointment = _booked(session, person.id, "huisarts")
    session.commit()
    commands.log_appointment_outcome(session, appointment, outcome=None, next_action=None)
    session.commit()
    assert obligation.last_done == date(2025, 1, 1)  # untouched


def test_log_outcome_uses_explicit_done_on_for_unscheduled(session):
    person = _person(session)
    obligation = commands.add_obligation(
        session, person.id, kind="tandarts", interval_months=6, last_done=date(2025, 1, 1)
    )
    appointment = commands.add_appointment(session, person.id, kind="tandarts")  # no scheduled_at
    session.commit()
    commands.log_appointment_outcome(
        session, appointment, outcome=None, next_action=None, done_on=date(2026, 7, 15)
    )
    session.commit()
    assert obligation.last_done == date(2026, 7, 15)


def test_add_contact_links_children_and_parent(session):
    alice = _person(session, "Alice")
    bob = _person(session, "Bob")
    session.commit()
    parent = commands.add_contact(session, name="Grace", kind=ContactKind.PARENT, phone="06-9")
    session.commit()
    friend = commands.add_contact(
        session,
        name="Robin",
        kind=ContactKind.FRIEND,
        parent_contact_id=parent.id,
        birthday=date(2016, 3, 3),
        linked_person_ids=(alice.id, bob.id),
    )
    session.commit()
    session.refresh(friend)
    assert friend.parent is parent
    assert {p.name for p in friend.linked_persons} == {"Alice", "Bob"}
    assert friend in alice.friends
