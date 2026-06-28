"""Model smoke tests: relationships resolve and enums store their values.

The recall and feed logic (the parts most worth testing) get dedicated
suites in later steps; this just pins the data model wiring.
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
    amber = Person(name="Amber", role=Role.CHILD)
    session.add(amber)
    session.flush()
    session.add(Appointment(person_id=amber.id, kind="tandarts", status=AppointmentStatus.DUE))
    session.add(RecurringObligation(person_id=amber.id, kind="tandarts", interval_months=6))
    session.add(VaccinationRecord(person_id=amber.id, vaccine="DKTP"))
    session.commit()
    session.refresh(amber)

    assert len(amber.appointments) == 1
    assert len(amber.obligations) == 1
    assert len(amber.vaccinations) == 1


def test_contact_graph(session):
    """kid -< link >- friend - parent_contact_id -> parent."""
    amber = Person(name="Amber", role=Role.CHILD)
    thomas = Person(name="Thomas", role=Role.CHILD)
    session.add_all([amber, thomas])
    session.flush()

    mum = Contact(name="Robin's mum", kind=ContactKind.PARENT, phone="06-1234")
    session.add(mum)
    session.flush()

    robin = Contact(
        name="Robin",
        kind=ContactKind.FRIEND,
        parent_contact_id=mum.id,
        birthday=date(2016, 3, 3),
    )
    robin.linked_persons.extend([amber, thomas])
    session.add(robin)
    session.commit()
    session.refresh(robin)

    # A friend belongs to multiple kids (many-to-many).
    assert {p.name for p in robin.linked_persons} == {"Amber", "Thomas"}
    assert robin in amber.friends
    # The friend's parent is stored once and reachable both ways.
    assert robin.parent is mum
    assert mum.dependents == [robin]


def test_role_stored_as_lowercase_value(session):
    """The non-native enum stores the member value, not its name."""
    session.add(Person(name="Oma", role=Role.ELDER))
    session.commit()

    stored = session.execute(text("SELECT role FROM person WHERE name = 'Oma'")).scalar_one()
    assert stored == "elder"
