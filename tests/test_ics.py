"""ICS invite upload: the parser (pure) and the upload -> review -> create flow,
including notes redaction, login-gating, and the upload size cap.
"""

from __future__ import annotations

import io
from datetime import datetime

import pytest

from hlin import auth, ics
from hlin.db import SessionLocal
from hlin.models import Person, Role, User


def _ics(*, dtstart="DTSTART:20260710T093000", summary="Tandarts controle", extra=""):
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:1@test\r\n"
        f"{dtstart}\r\nSUMMARY:{summary}\r\n{extra}"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


# --- parser (pure) ------------------------------------------------------


def test_parse_floating_event():
    event, count = ics.parse_invite(
        _ics(extra="LOCATION:Praktijk Centrum\r\nDESCRIPTION:Bring the insurance card\r\n")
    )
    assert count == 1
    assert event.kind_suggestion == "Tandarts controle"
    assert event.scheduled_at == datetime(2026, 7, 10, 9, 30)  # floating -> as-is, naive
    assert "Praktijk Centrum" in event.notes
    assert "insurance card" in event.notes


def test_parse_all_day_event_is_midnight():
    event, _ = ics.parse_invite(_ics(dtstart="DTSTART;VALUE=DATE:20260710"))
    assert event.scheduled_at == datetime(2026, 7, 10, 0, 0)


def test_parse_tz_aware_returns_naive_local():
    event, _ = ics.parse_invite(_ics(dtstart="DTSTART:20260710T093000Z"))
    # Converted to local wall time then made naive (exact hour is machine-local).
    assert event.scheduled_at is not None
    assert event.scheduled_at.tzinfo is None


def test_parse_notes_none_when_absent():
    event, _ = ics.parse_invite(_ics())
    assert event.notes is None


def test_parse_garbage_raises():
    with pytest.raises(ics.InvalidICS):
        ics.parse_invite(b"this is not a calendar at all")


def test_parse_no_vevent_raises():
    with pytest.raises(ics.InvalidICS):
        ics.parse_invite(b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\nEND:VCALENDAR\r\n")


def test_parse_multiple_events_takes_first_reports_count():
    two = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\n"
        "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20260710T090000\r\nSUMMARY:First\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:2\r\nDTSTART:20260711T090000\r\nSUMMARY:Second\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()
    event, count = ics.parse_invite(two)
    assert count == 2
    assert event.kind_suggestion == "First"


# --- upload -> review flow (client) -------------------------------------


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


def _upload(client, pid, data_bytes, filename="invite.ics"):
    return client.post(
        f"/person/{pid}/appointment/from-ics",
        data={"ics": (io.BytesIO(data_bytes), filename)},
        content_type="multipart/form-data",
        headers={"HX-Request": "true"},
    )


def test_upload_prefills_review_form_and_creates_nothing(client):
    _login(client)
    pid = _make_person()
    resp = _upload(client, pid, _ics(extra="LOCATION:Praktijk Centrum\r\n"))
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'value="Tandarts controle"' in body  # kind pre-filled
    assert "2026-07-10T09:30" in body  # when pre-filled
    assert "Praktijk Centrum" in body  # notes pre-filled
    # Parse-only: nothing persisted until the user submits the review form.
    with SessionLocal() as s:
        assert s.get(Person, pid).appointments == []


def test_upload_bad_file_shows_error_not_500(client):
    _login(client)
    pid = _make_person()
    resp = _upload(client, pid, b"garbage")
    assert resp.status_code == 200
    assert "iCalendar" in resp.get_data(as_text=True)


def test_upload_requires_login(client):
    pid = _make_person()
    resp = _upload(client, pid, _ics())
    assert resp.status_code == 401  # htmx -> 401 + HX-Redirect


def test_upload_over_size_cap_rejected(client):
    _login(client)
    pid = _make_person()
    resp = _upload(client, pid, b"x" * (1024 * 1024 + 16))
    assert resp.status_code == 413


# --- notes: persistence + redaction -------------------------------------


def test_notes_persist_and_redacted(client):
    _login(client)
    pid = _make_person()
    client.post(
        f"/person/{pid}/appointment",
        data={"kind": "tandarts", "status": "booked", "notes": "Praktijk Centrum, room 3"},
        headers={"HX-Request": "true"},
    )
    # Logged-in sees the notes on the person page.
    assert "Praktijk Centrum" in client.get(f"/person/{pid}").get_data(as_text=True)
    # Anonymous does not (sensitive field).
    client.post("/logout")
    assert "Praktijk Centrum" not in client.get(f"/person/{pid}").get_data(as_text=True)
