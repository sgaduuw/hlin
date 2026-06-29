"""CRUD route tests: add/edit/delete across persons and their children,
plus contacts. Exercises the login-gated mutation routes through the test
client and asserts the ownership guard (a child id under the wrong person
is a 404).
"""

from __future__ import annotations

from hlin import auth
from hlin.db import SessionLocal
from hlin.models import (
    Appointment,
    AppointmentStatus,
    Contact,
    ContactKind,
    Person,
    RecurringObligation,
    Role,
    User,
    VaccinationRecord,
)


def _login(client, username="linda", password="secret123"):
    with SessionLocal() as session:
        session.add(User(username=username, password_hash=auth.hash_password(password)))
        session.commit()
    client.post("/login", data={"username": username, "password": password})


def _make_person(name="Alice", role=Role.CHILD):
    with SessionLocal() as session:
        person = Person(name=name, role=role)
        session.add(person)
        session.commit()
        return person.id


# --- person -------------------------------------------------------------


def test_add_person(client):
    _login(client)
    resp = client.post("/person/new", data={"name": "Bob", "role": "adult"})
    assert resp.status_code == 302
    with SessionLocal() as session:
        people = session.query(Person).filter_by(name="Bob").all()
        assert len(people) == 1
        assert people[0].role == Role.ADULT


def test_add_person_rejects_bad_role(client):
    _login(client)
    resp = client.post("/person/new", data={"name": "Bob", "role": "wizard"})
    assert resp.status_code == 400


def test_edit_person(client):
    _login(client)
    pid = _make_person()
    client.post(
        f"/person/{pid}/edit",
        data={"name": "Alice B", "role": "child", "bsn": "123456782", "notes": "allergy"},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        person = session.get(Person, pid)
        assert person.name == "Alice B"
        assert person.bsn == "123456782"
        assert person.notes == "allergy"


def test_edit_person_blanks_become_null(client):
    _login(client)
    pid = _make_person()
    client.post(
        f"/person/{pid}/edit",
        data={"name": "Alice", "role": "child", "bsn": ""},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        assert session.get(Person, pid).bsn is None


def test_delete_person_cascades(client):
    _login(client)
    pid = _make_person()
    with SessionLocal() as session:
        session.add(Appointment(person_id=pid, kind="huisarts"))
        session.commit()
    resp = client.post(f"/person/{pid}/delete", headers={"HX-Request": "true"})
    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == "/"
    with SessionLocal() as session:
        assert session.get(Person, pid) is None
        assert session.query(Appointment).count() == 0


# --- appointment --------------------------------------------------------


def _make_appointment(person_id, kind="huisarts"):
    with SessionLocal() as session:
        appt = Appointment(person_id=person_id, kind=kind)
        session.add(appt)
        session.commit()
        return appt.id


def test_edit_appointment(client):
    _login(client)
    pid = _make_person()
    aid = _make_appointment(pid)
    client.post(
        f"/person/{pid}/appointment/{aid}/edit",
        data={"kind": "tandarts", "status": "booked"},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        appt = session.get(Appointment, aid)
        assert appt.kind == "tandarts"
        assert appt.status == AppointmentStatus.BOOKED


def test_delete_appointment(client):
    _login(client)
    pid = _make_person()
    aid = _make_appointment(pid)
    client.post(f"/person/{pid}/appointment/{aid}/delete", headers={"HX-Request": "true"})
    with SessionLocal() as session:
        assert session.get(Appointment, aid) is None


def test_child_ownership_guard(client):
    _login(client)
    owner = _make_person("Owner")
    other = _make_person("Other")
    aid = _make_appointment(owner)
    # The appointment belongs to `owner`; reaching it via `other` is a 404.
    resp = client.post(f"/person/{other}/appointment/{aid}/delete", headers={"HX-Request": "true"})
    assert resp.status_code == 404
    with SessionLocal() as session:
        assert session.get(Appointment, aid) is not None


# --- obligation ---------------------------------------------------------


def test_edit_obligation_toggles_active_off(client):
    _login(client)
    pid = _make_person()
    with SessionLocal() as session:
        ob = RecurringObligation(person_id=pid, kind="tandarts", interval_months=6)
        session.add(ob)
        session.commit()
        oid = ob.id
    # No `active` field in the form means the checkbox was unchecked.
    client.post(
        f"/person/{pid}/obligation/{oid}/edit",
        data={"kind": "tandarts", "interval_months": "12"},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        ob = session.get(RecurringObligation, oid)
        assert ob.interval_months == 12
        assert ob.active is False


def test_delete_obligation(client):
    _login(client)
    pid = _make_person()
    with SessionLocal() as session:
        ob = RecurringObligation(person_id=pid, kind="tandarts", interval_months=6)
        session.add(ob)
        session.commit()
        oid = ob.id
    client.post(f"/person/{pid}/obligation/{oid}/delete", headers={"HX-Request": "true"})
    with SessionLocal() as session:
        assert session.get(RecurringObligation, oid) is None


# --- vaccination --------------------------------------------------------


def test_vaccination_add_edit_delete(client):
    _login(client)
    pid = _make_person()
    client.post(
        f"/person/{pid}/vaccination",
        data={"vaccine": "BMR", "where": "GGD"},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        rec = session.query(VaccinationRecord).filter_by(person_id=pid).one()
        vid = rec.id
        assert rec.vaccine == "BMR"
    client.post(
        f"/person/{pid}/vaccination/{vid}/edit",
        data={"vaccine": "BMR-2", "where": ""},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        rec = session.get(VaccinationRecord, vid)
        assert rec.vaccine == "BMR-2"
        assert rec.where is None
    client.post(f"/person/{pid}/vaccination/{vid}/delete", headers={"HX-Request": "true"})
    with SessionLocal() as session:
        assert session.get(VaccinationRecord, vid) is None


# --- contact ------------------------------------------------------------


def _make_contact(name="Sam", kind=ContactKind.FRIEND):
    with SessionLocal() as session:
        contact = Contact(name=name, kind=kind)
        session.add(contact)
        session.commit()
        return contact.id


def test_edit_contact(client):
    _login(client)
    cid = _make_contact()
    client.post(
        f"/contacts/{cid}/edit",
        data={"name": "Sammy", "kind": "friend", "phone": "0612345678"},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        contact = session.get(Contact, cid)
        assert contact.name == "Sammy"
        assert contact.phone == "0612345678"


def test_delete_contact(client):
    _login(client)
    cid = _make_contact()
    client.post(f"/contacts/{cid}/delete", headers={"HX-Request": "true"})
    with SessionLocal() as session:
        assert session.get(Contact, cid) is None


def test_contact_cannot_be_its_own_parent(client):
    _login(client)
    cid = _make_contact(kind=ContactKind.PARENT)
    client.post(
        f"/contacts/{cid}/edit",
        data={"name": "Sam", "kind": "parent", "parent_contact_id": str(cid)},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as session:
        assert session.get(Contact, cid).parent_contact_id is None


# --- gating -------------------------------------------------------------


def test_anonymous_cannot_delete_person(client):
    pid = _make_person()
    resp = client.post(f"/person/{pid}/delete")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    with SessionLocal() as session:
        assert session.get(Person, pid) is not None


def test_anonymous_cannot_edit_contact(client):
    cid = _make_contact()
    resp = client.post(f"/contacts/{cid}/edit", data={"name": "x"}, headers={"HX-Request": "true"})
    assert resp.status_code == 401


# --- render smokes for the logged-in editor affordances -----------------


def test_dashboard_and_contacts_render_logged_in(client):
    # Exercises the add-person form and the contacts edit macro, which only
    # render for logged-in users, so a Jinja error in them fails here.
    _login(client)
    pid = _make_person()
    _make_contact(kind=ContactKind.PARENT)  # shows in "other contacts", drives the edit macro
    with SessionLocal() as session:
        session.add(VaccinationRecord(person_id=pid, vaccine="BMR"))
        session.commit()
    assert b"Add person" in client.get("/").data
    contacts = client.get("/contacts/").data
    assert b"Add contact" in contacts
    assert b'name="parent_contact_id"' in contacts  # the edit macro's parent picker
    assert b"Edit person" in client.get(f"/person/{pid}").data
