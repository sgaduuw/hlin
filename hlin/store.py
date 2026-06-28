"""Read queries: the SELECT side of the data model.

Kept in one place so the views and feeds stay about presentation while the
query shapes and the small per-person derivations live together. All
functions take a ``Session`` or an already-loaded ``Person``; nothing here
writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Appointment, AppointmentStatus, Contact, Person, RecurringObligation


def list_persons(session: Session) -> Sequence[Person]:
    return session.scalars(select(Person).order_by(Person.role, Person.name)).all()


def get_person(session: Session, person_id: int) -> Person | None:
    return session.get(Person, person_id)


def active_obligations(session: Session) -> Sequence[RecurringObligation]:
    return session.scalars(
        select(RecurringObligation).where(RecurringObligation.active.is_(True))
    ).all()


def booked_appointments(session: Session) -> Sequence[Appointment]:
    return session.scalars(
        select(Appointment).where(Appointment.status == AppointmentStatus.BOOKED)
    ).all()


def list_contacts(session: Session) -> Sequence[Contact]:
    return session.scalars(select(Contact).order_by(Contact.name)).all()


# --- per-person derivations (operate on a loaded Person) -----------------


def next_appointment(person: Person, *, today: date) -> Appointment | None:
    """The soonest booked, scheduled appointment that is not in the past."""
    upcoming = [
        a
        for a in person.appointments
        if a.status == AppointmentStatus.BOOKED
        and a.scheduled_at is not None
        and a.scheduled_at.date() >= today
    ]
    return min(upcoming, key=lambda a: a.scheduled_at, default=None)


def open_follow_ups(person: Person) -> list[Appointment]:
    """Appointments that generated a follow-up that has not been closed out."""
    return [a for a in person.appointments if a.next_action and a.status != AppointmentStatus.DONE]
