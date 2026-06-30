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
    Role,
    VaccinationRecord,
)


def _linked_persons(session: Session, person_ids: tuple[int, ...]) -> list[Person]:
    if not person_ids:
        return []
    return list(session.scalars(select(Person).where(Person.id.in_(person_ids))).all())


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
) -> None:
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
    contact.linked_persons = _linked_persons(session, linked_person_ids)
    session.add(contact)
    return contact


# --- person ------------------------------------------------------------


def add_person(
    session: Session,
    *,
    name: str,
    role: Role,
    date_of_birth: date | None = None,
    bsn: str | None = None,
    huisarts: str | None = None,
    tandarts: str | None = None,
    notes: str | None = None,
) -> Person:
    person = Person(
        name=name,
        role=role,
        date_of_birth=date_of_birth,
        bsn=bsn,
        huisarts=huisarts,
        tandarts=tandarts,
        notes=notes,
    )
    session.add(person)
    return person


def update_person(
    person: Person,
    *,
    name: str,
    role: Role,
    date_of_birth: date | None,
    bsn: str | None,
    huisarts: str | None,
    tandarts: str | None,
    notes: str | None,
) -> None:
    person.name = name
    person.role = role
    person.date_of_birth = date_of_birth
    person.bsn = bsn or None
    person.huisarts = huisarts or None
    person.tandarts = tandarts or None
    person.notes = notes or None


# --- appointment / obligation edits ------------------------------------


def update_appointment(
    appointment: Appointment,
    *,
    kind: str,
    scheduled_at: datetime | None,
    status: AppointmentStatus,
) -> None:
    appointment.kind = kind
    appointment.scheduled_at = scheduled_at
    appointment.status = status


def update_obligation(
    obligation: RecurringObligation,
    *,
    kind: str,
    interval_months: int,
    last_done: date | None,
    active: bool,
) -> None:
    obligation.kind = kind
    obligation.interval_months = interval_months
    obligation.last_done = last_done
    obligation.active = active


# --- vaccination -------------------------------------------------------


def add_vaccination(
    session: Session,
    person_id: int,
    *,
    vaccine: str,
    date: date | None = None,
    where: str | None = None,
    notes: str | None = None,
) -> VaccinationRecord:
    record = VaccinationRecord(
        person_id=person_id, vaccine=vaccine, date=date, where=where, notes=notes
    )
    session.add(record)
    return record


def update_vaccination(
    record: VaccinationRecord,
    *,
    vaccine: str,
    date: date | None,
    where: str | None,
    notes: str | None,
) -> None:
    record.vaccine = vaccine
    record.date = date
    record.where = where or None
    record.notes = notes or None


# --- contact edit ------------------------------------------------------


def update_contact(
    session: Session,
    contact: Contact,
    *,
    name: str,
    kind: ContactKind,
    parent_contact_id: int | None,
    phone: str | None,
    email: str | None,
    birthday: date | None,
    linked_person_ids: tuple[int, ...],
) -> None:
    contact.name = name
    contact.kind = kind
    # A contact cannot be its own parent.
    contact.parent_contact_id = parent_contact_id if parent_contact_id != contact.id else None
    contact.phone = phone or None
    contact.email = email or None
    contact.birthday = birthday
    contact.linked_persons = _linked_persons(session, linked_person_ids)
