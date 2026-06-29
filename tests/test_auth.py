"""Auth tests: password hashing, open-redirect prevention, and the
read-open / edit-gated / sensitive-redacted boundary via the test client.
"""

from __future__ import annotations

import pytest

from hlin import auth
from hlin.db import SessionLocal
from hlin.models import Person, Role, User

# --- pure functions (security-critical) ---------------------------------


def test_hash_and_verify_roundtrip():
    user = User(username="x", password_hash=auth.hash_password("hunter2"))
    assert auth.verify_password(user, "hunter2")


def test_verify_rejects_wrong_password():
    user = User(username="x", password_hash=auth.hash_password("hunter2"))
    assert not auth.verify_password(user, "nope")


def test_hash_is_salted():
    assert auth.hash_password("same") != auth.hash_password("same")


@pytest.mark.parametrize(
    "target,expected",
    [
        ("/person/1", "/person/1"),
        ("/", "/"),
        ("//evil.com", None),
        ("https://evil.com", None),
        ("javascript:alert(1)", None),
        ("", None),
        (None, None),
    ],
)
def test_safe_next_only_allows_local(target, expected):
    assert auth.safe_next(target) == expected


# --- route behaviour ----------------------------------------------------


def _make_user(username="linda", password="secret123"):
    with SessionLocal() as session:
        session.add(User(username=username, password_hash=auth.hash_password(password)))
        session.commit()


def _make_person(name="Alice", *, bsn=None, notes=None):
    with SessionLocal() as session:
        person = Person(name=name, role=Role.CHILD, bsn=bsn, notes=notes)
        session.add(person)
        session.commit()
        return person.id


def _login(client, username="linda", password="secret123"):
    return client.post("/login", data={"username": username, "password": password})


def test_login_rejects_bad_credentials(client):
    _make_user()
    assert _login(client, password="wrong").status_code == 401


def test_login_accepts_good_credentials(client):
    _make_user()
    resp = _login(client)
    assert resp.status_code == 302


def test_anonymous_mutation_is_blocked_htmx(client):
    pid = _make_person()
    resp = client.post(
        f"/person/{pid}/appointment", data={"kind": "huisarts"}, headers={"HX-Request": "true"}
    )
    assert resp.status_code == 401
    assert resp.headers.get("HX-Redirect") == "/login"


def test_anonymous_mutation_redirects_non_htmx(client):
    pid = _make_person()
    resp = client.post(f"/person/{pid}/appointment", data={"kind": "huisarts"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logged_in_mutation_succeeds(client):
    _make_user()
    pid = _make_person()
    _login(client)
    resp = client.post(
        f"/person/{pid}/appointment",
        data={"kind": "huisarts", "status": "due"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    with SessionLocal() as session:
        person = session.get(Person, pid)
        assert len(person.appointments) == 1


def test_sensitive_fields_redacted_for_anonymous(client):
    pid = _make_person(bsn="123456782", notes="penicillin allergy")
    body = client.get(f"/person/{pid}").get_data(as_text=True)
    assert "123456782" not in body
    assert "penicillin" not in body
    assert "🔒" in body


def test_sensitive_fields_visible_when_logged_in(client):
    _make_user()
    pid = _make_person(bsn="123456782", notes="penicillin allergy")
    _login(client)
    body = client.get(f"/person/{pid}").get_data(as_text=True)
    assert "123456782" in body
    assert "penicillin allergy" in body
