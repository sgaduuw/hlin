"""Write operations (the mutation side of the data model).

One place for the writes the quick-add / logging flow performs, kept apart
from the read queries in ``store``. Each function takes the request's
``Session`` and leaves the commit to the caller, so a route runs exactly
one connection and one transaction per request (portfolio rule: never open
a second ``SessionLocal`` inside a handler).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Appointment,
    AppointmentStatus,
    Contact,
    ContactKind,
    Person,
    RecurringObligation,
)


def add_appointment(
    session: Session,
    person_id: int,
    *,
    kind: str,
    scheduled_at: datetime | None = None,
    status: AppointmentStatus = AppointmentStatus.DUE,
) -> Appointment:
    appointment = Appointment(
        person_id=person_id, kind=kind, scheduled_at=scheduled_at, status=status
    )
    session.add(appointment)
    return appointment


def add_obligation(
    session: Session,
    person_id: int,
    *,
    kind: str,
    interval_months: int,
    last_done: date | None = None,
) -> RecurringObligation:
    obligation = RecurringObligation(
        person_id=person_id, kind=kind, interval_months=interval_months, last_done=last_done
    )
    session.add(obligation)
    return obligation


def log_appointment_outcome(
    session: Session,
    appointment: Appointment,
    *,
    outcome: str | None,
    next_action: str | None,
    done_on: date | None = None,
) -> Appointment:
    """Mark an appointment done and record its outcome, then advance any
    matching recurring obligation's ``last_done`` so the next-due date rolls
    forward. The obligation cascade is the spec's "mark done updates the
    obligation" behaviour; it only ever moves ``last_done`` forward."""
    appointment.status = AppointmentStatus.DONE
    appointment.outcome = outcome or None
    appointment.next_action = next_action or None

    completed_on = done_on or (
        appointment.scheduled_at.date() if appointment.scheduled_at else date.today()
    )
    obligation = session.scalar(
        select(RecurringObligation).where(
            RecurringObligation.person_id == appointment.person_id,
            RecurringObligation.kind == appointment.kind,
            RecurringObligation.active.is_(True),
        )
    )
    if obligation is not None and (
        obligation.last_done is None or obligation.last_done < completed_on
    ):
        obligation.last_done = completed_on
    return appointment


def add_contact(
    session: Session,
    *,
    name: str,
    kind: ContactKind = ContactKind.FRIEND,
    parent_contact_id: int | None = None,
    phone: str | None = None,
    email: str | None = None,
    birthday: date | None = None,
    linked_person_ids: tuple[int, ...] = (),
) -> Contact:
    contact = Contact(
        name=name,
        kind=kind,
        parent_contact_id=parent_contact_id,
        phone=phone,
        email=email,
        birthday=birthday,
    )
    if linked_person_ids:
        contact.linked_persons.extend(
            session.scalars(select(Person).where(Person.id.in_(linked_person_ids))).all()
        )
    session.add(contact)
    return contact
