"""Model smoke tests: relationships resolve and enums store their values.

The recall and feed logic (the parts most worth testing) get dedicated
suites in later steps; this just pins the data model wiring. Fixture names
are anonymous placeholders (Alice/Bob/...).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from hlin.models import (
    Appointment,
    AppointmentStatus,
    Contact,
    ContactKind,
    Person,
    RecurringObligation,
    Role,
    VaccinationRecord,
)


def test_person_care_relationships(session):
    alice = Person(name="Alice", role=Role.CHILD)
    session.add(alice)
    session.flush()
    session.add(Appointment(person_id=alice.id, kind="tandarts", status=AppointmentStatus.DUE))
    session.add(RecurringObligation(person_id=alice.id, kind="tandarts", interval_months=6))
    session.add(VaccinationRecord(person_id=alice.id, vaccine="DKTP"))
    session.commit()
    session.refresh(alice)

    assert len(alice.appointments) == 1
    assert len(alice.obligations) == 1
    assert len(alice.vaccinations) == 1


def test_contact_graph(session):
    """kid -< link >- friend - parent_contact_id -> parent."""
    alice = Person(name="Alice", role=Role.CHILD)
    bob = Person(name="Bob", role=Role.CHILD)
    session.add_all([alice, bob])
    session.flush()

    parent = Contact(name="Frank's parent", kind=ContactKind.PARENT, phone="06-1234")
    session.add(parent)
    session.flush()

    frank = Contact(
        name="Frank",
        kind=ContactKind.FRIEND,
        parent_contact_id=parent.id,
        birthday=date(2016, 3, 3),
    )
    frank.linked_persons.extend([alice, bob])
    session.add(frank)
    session.commit()
    session.refresh(frank)

    # A friend belongs to multiple kids (many-to-many).
    assert {p.name for p in frank.linked_persons} == {"Alice", "Bob"}
    assert frank in alice.friends
    # The friend's parent is stored once and reachable both ways.
    assert frank.parent is parent
    assert parent.dependents == [frank]


def test_role_stored_as_lowercase_value(session):
    """The non-native enum stores the member value, not its name."""
    session.add(Person(name="Erin", role=Role.ELDER))
    session.commit()

    stored = session.execute(text("SELECT role FROM person WHERE name = 'Erin'")).scalar_one()
    assert stored == "elder"
