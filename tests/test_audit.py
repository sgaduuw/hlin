"""Audit-log tests: atomic capture (action / actor / target), the no-request
(CLI) actor fallback, and the /audit page gating, ordering, and filter.
"""

from __future__ import annotations

from sqlalchemy import select

from hlin import audit, auth
from hlin.audit import AuditAction
from hlin.db import SessionLocal
from hlin.models import Appointment, AuditLog, Person, Role, User


def _login(client, username="linda", password="secret123"):
    with SessionLocal() as s:
        s.add(User(username=username, password_hash=auth.hash_password(password)))
        s.commit()
    client.post("/login", data={"username": username, "password": password})


def _make_person(name="Alice"):
    with SessionLocal() as s:
        p = Person(name=name, role=Role.CHILD)
        s.add(p)
        s.commit()
        return p.id


def _rows(action=None):
    with SessionLocal() as s:
        stmt = select(AuditLog).order_by(AuditLog.id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return list(s.scalars(stmt).all())


def _add_appointment(client, pid, kind="huisarts"):
    client.post(
        f"/person/{pid}/appointment", data={"kind": kind}, headers={"HX-Request": "true"}
    )
    return _rows(AuditAction.APPOINTMENT_CREATE)[-1].target_id


# --- capture ------------------------------------------------------------


def test_create_writes_one_atomic_audit_row(client):
    _login(client)
    pid = _make_person()
    _add_appointment(client, pid, "huisarts")
    rows = _rows(AuditAction.APPOINTMENT_CREATE)
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_username == "linda"
    assert row.target_type == "appointment"
    assert row.target_id is not None  # flush assigned the id before auditing
    assert row.summary == "huisarts for Alice"


def test_actor_user_id_matches_logged_in_user(client):
    _login(client)
    pid = _make_person()
    client.post(
        f"/person/{pid}/edit",
        data={"name": "Alice B", "role": "child"},
        headers={"HX-Request": "true"},
    )
    row = _rows(AuditAction.PERSON_UPDATE)[0]
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.username == "linda"))
        assert row.actor_user_id == user.id


def test_delete_audit_row_outlives_the_target(client):
    _login(client)
    pid = _make_person()
    aid = _add_appointment(client, pid, "tandarts")
    client.post(f"/person/{pid}/appointment/{aid}/delete", headers={"HX-Request": "true"})
    drow = _rows(AuditAction.APPOINTMENT_DELETE)[0]
    assert drow.target_id == aid
    assert drow.summary == "tandarts for Alice"
    with SessionLocal() as s:
        assert s.get(Appointment, aid) is None  # the row it documents is gone


def test_log_outcome_is_audited(client):
    _login(client)
    pid = _make_person()
    aid = _add_appointment(client, pid)
    client.post(
        f"/person/{pid}/appointment/{aid}/outcome",
        data={"outcome": "seen"},
        headers={"HX-Request": "true"},
    )
    assert len(_rows(AuditAction.APPOINTMENT_LOG_OUTCOME)) == 1


def test_record_outside_request_has_no_actor(session):
    # CLI / system mutation: no request context -> actor is None, row still written.
    person = Person(name="Bob", role=Role.ADULT)
    session.add(person)
    session.flush()
    audit.record(session, AuditAction.PERSON_CREATE, person)
    session.commit()
    row = session.scalar(select(AuditLog))
    assert row.actor_user_id is None
    assert row.actor_username is None
    assert row.target_type == "person"
    assert row.target_id == person.id


# --- the /audit page ----------------------------------------------------


def test_audit_page_requires_login(client):
    resp = client.get("/audit/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_audit_page_lists_newest_first(client):
    _login(client)
    pid = _make_person()
    _add_appointment(client, pid, "huisarts")
    client.post(
        f"/person/{pid}/obligation",
        data={"kind": "tandarts", "interval_months": "6"},
        headers={"HX-Request": "true"},
    )
    body = client.get("/audit/").get_data(as_text=True)
    # Summaries appear only in the table (not the action-filter dropdown), so
    # they cleanly prove ordering: the obligation was created last -> shows first.
    assert body.index("tandarts for Alice") < body.index("huisarts for Alice")


def test_audit_page_filter_by_action(client):
    _login(client)
    pid = _make_person()
    _add_appointment(client, pid, "huisarts")
    client.post(
        f"/person/{pid}/obligation",
        data={"kind": "tandarts", "interval_months": "6"},
        headers={"HX-Request": "true"},
    )
    body = client.get("/audit/?action=appointment.create").get_data(as_text=True)
    assert "huisarts for Alice" in body  # appointment.create row present
    assert "tandarts for Alice" not in body  # obligation.create row filtered out
