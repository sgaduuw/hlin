"""First-run household seed.

EDIT the ``SEED_*`` tables below for your own household. Re-running the
seed is idempotent: persons are matched by name and obligations by
(person, kind), so only missing rows are inserted. Run it with::

    uv run flask --app hlin seed
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Person, RecurringObligation, Role

# (name, role, date_of_birth): anonymous placeholders for the dev env.
# Replace with your real household before relying on the seed.
SEED_PERSONS: list[tuple[str, Role, date | None]] = [
    ("Alice", Role.CHILD, date(2016, 5, 1)),
    ("Bob", Role.CHILD, date(2019, 9, 12)),
    ("Carol", Role.ADULT, None),
    ("Dave", Role.ADULT, None),
    ("Erin", Role.ELDER, None),
]

# (person_name, kind, interval_months): initial recurring obligations.
# Mixed cadences/roles so the dev env exercises the recall logic broadly.
SEED_OBLIGATIONS: list[tuple[str, str, int]] = [
    ("Alice", "tandarts", 6),
    ("Bob", "tandarts", 6),
    ("Erin", "huisarts", 3),
]


def seed_household(session: Session) -> int:
    """Insert any missing seed persons/obligations. Returns rows created."""
    created = 0
    by_name: dict[str, Person] = {}

    for name, role, dob in SEED_PERSONS:
        person = session.scalar(select(Person).where(Person.name == name))
        if person is None:
            person = Person(name=name, role=role, date_of_birth=dob)
            session.add(person)
            session.flush()  # assign id for the obligation pass below
            created += 1
        by_name[name] = person

    for person_name, kind, interval_months in SEED_OBLIGATIONS:
        person = by_name.get(person_name)
        if person is None:
            continue
        existing = session.scalar(
            select(RecurringObligation).where(
                RecurringObligation.person_id == person.id,
                RecurringObligation.kind == kind,
            )
        )
        if existing is None:
            session.add(
                RecurringObligation(person_id=person.id, kind=kind, interval_months=interval_months)
            )
            created += 1

    return created
