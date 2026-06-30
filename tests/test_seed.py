"""Seed tests: seed_household inserts the configured persons/obligations,
returns the created count, and is idempotent (persons matched by name,
obligations by (person, kind), so re-running creates nothing new).
"""

from __future__ import annotations

from sqlalchemy import func, select

from hlin.models import Person, RecurringObligation
from hlin.seed_data import SEED_OBLIGATIONS, SEED_PERSONS, seed_household


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_seed_creates_configured_rows(session):
    created = seed_household(session)
    session.commit()
    assert created == len(SEED_PERSONS) + len(SEED_OBLIGATIONS)
    assert _count(session, Person) == len(SEED_PERSONS)
    assert _count(session, RecurringObligation) == len(SEED_OBLIGATIONS)


def test_seed_is_idempotent(session):
    seed_household(session)
    session.commit()
    created_again = seed_household(session)
    session.commit()
    assert created_again == 0
    assert _count(session, Person) == len(SEED_PERSONS)
    assert _count(session, RecurringObligation) == len(SEED_OBLIGATIONS)


def test_seed_reuses_existing_person_by_name(session):
    # A person already present by name is reused (matched by name), not
    # duplicated; only the missing rows get created.
    name, role, _dob = SEED_PERSONS[0]
    session.add(Person(name=name, role=role))
    session.commit()
    seed_household(session)
    session.commit()
    same_name = session.scalar(select(func.count()).select_from(Person).where(Person.name == name))
    assert same_name == 1
    assert _count(session, Person) == len(SEED_PERSONS)
