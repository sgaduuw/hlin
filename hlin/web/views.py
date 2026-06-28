"""HTML views: the dashboard, the per-person page, and the person-page
write actions (quick-add appointment / obligation, log an outcome).

Reads render inside the ``SessionLocal()`` block so templates can follow
relationships lazily. Writes run one transaction, then ``expire`` the
person so the re-rendered fragment reflects the new state (appointments,
and any obligation whose ``last_done`` the cascade just advanced). The
actions return the ``_person_main`` fragment for htmx to swap in place.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, render_template, request

from .. import commands, store
from ..db import SessionLocal
from ..models import APPOINTMENT_KINDS, Appointment, AppointmentStatus, Role
from ..recall import next_due_date, obligations_needing_attention
from ..settings import settings
from ._forms import parse_date, parse_datetime

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


def _person_context(person) -> dict:
    today = date.today()
    return {
        "person": person,
        "appointments": sorted(person.appointments, key=lambda a: a.created_at, reverse=True),
        "follow_ups": store.open_follow_ups(person),
        "ob_rows": [(o, next_due_date(o, today=today)) for o in person.obligations],
        "kinds": APPOINTMENT_KINDS,
    }


def _require_person(session, person_id: int):
    person = store.get_person(session, person_id)
    if person is None:
        abort(404)
    return person


@bp.get("/person/<int:person_id>")
def person(person_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        return render_template("person.html", **_person_context(target))


@bp.post("/person/<int:person_id>/appointment")
def add_appointment(person_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        kind = request.form.get("kind", "").strip()
        if not kind:
            abort(400)
        commands.add_appointment(
            session,
            person_id,
            kind=kind,
            scheduled_at=parse_datetime(request.form.get("scheduled_at")),
            status=AppointmentStatus(request.form.get("status", "due")),
        )
        session.commit()
        session.expire(target)
        return render_template("_person_main.html", **_person_context(target))


@bp.post("/person/<int:person_id>/obligation")
def add_obligation(person_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        kind = request.form.get("kind", "").strip()
        interval = request.form.get("interval_months", "").strip()
        if not kind or not interval.isdigit():
            abort(400)
        commands.add_obligation(
            session,
            person_id,
            kind=kind,
            interval_months=int(interval),
            last_done=parse_date(request.form.get("last_done")),
        )
        session.commit()
        session.expire(target)
        return render_template("_person_main.html", **_person_context(target))


@bp.post("/person/<int:person_id>/appointment/<int:appointment_id>/outcome")
def log_outcome(person_id: int, appointment_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        appointment = session.get(Appointment, appointment_id)
        if appointment is None or appointment.person_id != person_id:
            abort(404)
        commands.log_appointment_outcome(
            session,
            appointment,
            outcome=request.form.get("outcome", "").strip() or None,
            next_action=request.form.get("next_action", "").strip() or None,
        )
        session.commit()
        session.expire(target)
        return render_template("_person_main.html", **_person_context(target))
