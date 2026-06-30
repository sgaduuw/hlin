"""User<->Person identity link: the link helper's validation, the CLI
link command, the login storing the linked person, and the nav "my page"
shortcut (present only when linked).
"""

from __future__ import annotations

import click
import pytest
from sqlalchemy import select

from hlin import auth, create_app
from hlin.cli import _link_person
from hlin.db import SessionLocal
from hlin.models import Person, Role, User


def _person(session, name="Linda", role=Role.ADULT):
    p = Person(name=name, role=role)
    session.add(p)
    session.flush()
    return p


# --- link helper validation (session fixture, no request) ---------------


def test_link_person_success(session):
    p = _person(session)
    u = User(username="linda", password_hash="x")
    session.add(u)
    session.flush()
    _link_person(session, u, p.id)
    assert u.person_id == p.id


def test_link_person_rejects_missing_person(session):
    u = User(username="x", password_hash="x")
    session.add(u)
    session.flush()
    with pytest.raises(click.ClickException):
        _link_person(session, u, 9999)


def test_link_person_rejects_already_claimed(session):
    p = _person(session)
    u1 = User(username="a", password_hash="x")
    u2 = User(username="b", password_hash="x")
    session.add_all([u1, u2])
    session.flush()
    _link_person(session, u1, p.id)
    session.flush()
    with pytest.raises(click.ClickException):
        _link_person(session, u2, p.id)


# --- CLI end-to-end -----------------------------------------------------


def test_cli_user_link(client):
    # `client` fixture has created the schema on the app engine.
    with SessionLocal() as s:
        p = _person(s)
        s.add(User(username="linda", password_hash="x"))
        s.commit()
        pid = p.id
    result = create_app().test_cli_runner().invoke(args=["user", "link", "linda", str(pid)])
    assert result.exit_code == 0, result.output
    with SessionLocal() as s:
        assert s.scalar(select(User).where(User.username == "linda")).person_id == pid


# --- login + nav shortcut -----------------------------------------------


def _make_login(username, password, *, person_id=None):
    with SessionLocal() as s:
        s.add(
            User(
                username=username,
                password_hash=auth.hash_password(password),
                person_id=person_id,
            )
        )
        s.commit()


def test_linked_login_nav_shows_my_page(client):
    with SessionLocal() as s:
        p = _person(s)
        s.commit()
        pid = p.id
    _make_login("linda", "secret123", person_id=pid)
    client.post("/login", data={"username": "linda", "password": "secret123"})
    body = client.get("/").get_data(as_text=True)
    assert f"/person/{pid}" in body  # the nav links the username to the person page


def test_unlinked_login_has_no_person_link(client):
    # No persons exist, so an unlinked login yields no /person/ link anywhere.
    _make_login("bob", "secret123")
    client.post("/login", data={"username": "bob", "password": "secret123"})
    body = client.get("/").get_data(as_text=True)
    assert "bob" in body
    # The "my page" shortcut is an href to a person page; absent when unlinked.
    # (The add-person form's action="/person/new" is not an href, so excluded.)
    assert 'href="/person/' not in body
