"""HTML read views: the dashboard and the per-person page.

Rendering happens inside the ``SessionLocal()`` block so the templates can
follow relationships lazily; the views are read-only (no commit). Pure
recall/derivation lives in ``recall`` and ``store``; this module only
assembles view data and renders.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, render_template

from .. import store
from ..db import SessionLocal
from ..models import Role
from ..recall import next_due_date, obligations_needing_attention
from ..settings import settings

bp = Blueprint("views", __name__)

# (role, dashboard heading) in display order.
_ROLE_GROUPS: list[tuple[Role, str]] = [
    (Role.CHILD, "Kids"),
    (Role.ADULT, "Adults"),
    (Role.ELDER, "Grandparents"),
]


@bp.get("/")
def dashboard():
    today = date.today()
    with SessionLocal() as session:
        persons = store.list_persons(session)
        panel = obligations_needing_attention(
            store.active_obligations(session),
            store.booked_appointments(session),
            today=today,
            horizon_days=settings.horizon_days,
        )
        groups = []
        for role, label in _ROLE_GROUPS:
            cards = [
                {
                    "person": person,
                    "next_appointment": store.next_appointment(person, today=today),
                    "open_follow_ups": len(store.open_follow_ups(person)),
                }
                for person in persons
                if person.role == role
            ]
            groups.append((label, cards))
        return render_template("dashboard.html", panel=panel, groups=groups)


@bp.get("/person/<int:person_id>")
def person(person_id: int):
    today = date.today()
    with SessionLocal() as session:
        person = store.get_person(session, person_id)
        if person is None:
            abort(404)
        return render_template(
            "person.html",
            person=person,
            appointments=sorted(person.appointments, key=lambda a: a.created_at, reverse=True),
            follow_ups=store.open_follow_ups(person),
            ob_rows=[(o, next_due_date(o, today=today)) for o in person.obligations],
        )
