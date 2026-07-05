"""Hardening tests from the security sweep: input-validation 400s (interval
bound, invalid enum, tolerant date parsing) and the security response headers.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from werkzeug.exceptions import BadRequest

from hlin import auth
from hlin.db import SessionLocal
from hlin.models import AppointmentStatus, Person, Role, User
from hlin.web._forms import enum_field, parse_date, parse_datetime


def _login(client):
    with SessionLocal() as s:
        s.add(User(username="linda", password_hash=auth.hash_password("secret123")))
        s.commit()
    client.post("/login", data={"username": "linda", "password": "secret123"})


def _make_person(name="Alice"):
    with SessionLocal() as s:
        p = Person(name=name, role=Role.CHILD)
        s.add(p)
        s.commit()
        return p.id


# --- pure form helpers --------------------------------------------------


def test_parse_date_tolerant():
    assert parse_date("2026-07-05") == date(2026, 7, 5)
    assert parse_date("garbage") is None  # was a ValueError -> 500
    assert parse_date("") is None
    assert parse_date(None) is None


def test_parse_datetime_tolerant():
    assert parse_datetime("2026-07-05T09:30") == datetime(2026, 7, 5, 9, 30)
    assert parse_datetime("nope") is None


def test_enum_field():
    assert (
        enum_field(AppointmentStatus, "booked", default=AppointmentStatus.DUE)
        is AppointmentStatus.BOOKED
    )
    assert enum_field(AppointmentStatus, "", default=AppointmentStatus.DUE) is AppointmentStatus.DUE
    assert (
        enum_field(AppointmentStatus, None, default=AppointmentStatus.DUE) is AppointmentStatus.DUE
    )
    with pytest.raises(BadRequest):
        enum_field(AppointmentStatus, "bogus", default=AppointmentStatus.DUE)


# --- routes: crafted input is a 400, not a 500 --------------------------


def test_obligation_rejects_huge_interval(client):
    _login(client)
    pid = _make_person()
    # A huge interval would overflow the derived next-due date and 500 the
    # anonymous dashboard/feeds; it must be rejected up front.
    bad = client.post(
        f"/person/{pid}/obligation",
        data={"kind": "tandarts", "interval_months": "100000"},
        headers={"HX-Request": "true"},
    )
    assert bad.status_code == 400
    # A unicode digit (isdigit() True but int() raises) is also a 400, not a 500.
    uni = client.post(
        f"/person/{pid}/obligation",
        data={"kind": "tandarts", "interval_months": "²"},
        headers={"HX-Request": "true"},
    )
    assert uni.status_code == 400
    ok = client.post(
        f"/person/{pid}/obligation",
        data={"kind": "tandarts", "interval_months": "6"},
        headers={"HX-Request": "true"},
    )
    assert ok.status_code == 200


def test_invalid_appointment_status_is_400(client):
    _login(client)
    pid = _make_person()
    resp = client.post(
        f"/person/{pid}/appointment",
        data={"kind": "huisarts", "status": "bogus"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 400


def test_invalid_contact_kind_is_400(client):
    _login(client)
    resp = client.post(
        "/contacts/", data={"name": "Sam", "kind": "bogus"}, headers={"HX-Request": "true"}
    )
    assert resp.status_code == 400


def test_malformed_date_is_ignored_not_500(client):
    _login(client)
    pid = _make_person()
    resp = client.post(
        f"/person/{pid}/appointment",
        data={"kind": "huisarts", "scheduled_at": "not-a-date"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200  # the bad date is treated as absent


# --- HTTP security headers ----------------------------------------------


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
