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

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

from .. import auth, commands, store
from ..db import SessionLocal
from ..models import (
    APPOINTMENT_KINDS,
    Appointment,
    AppointmentStatus,
    RecurringObligation,
    Role,
    VaccinationRecord,
)
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
        return render_template("dashboard.html", panel=panel, groups=groups, roles=_ROLE_VALUES)


_ROLE_VALUES = [role.value for role in Role]
_STATUS_VALUES = [status.value for status in AppointmentStatus]


def _person_context(person) -> dict:
    today = date.today()
    return {
        "person": person,
        "appointments": sorted(person.appointments, key=lambda a: a.created_at, reverse=True),
        "follow_ups": store.open_follow_ups(person),
        "ob_rows": [(o, next_due_date(o, today=today)) for o in person.obligations],
        "kinds": APPOINTMENT_KINDS,
        "roles": _ROLE_VALUES,
        "statuses": _STATUS_VALUES,
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
@auth.login_required
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
@auth.login_required
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
@auth.login_required
def log_outcome(person_id: int, appointment_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        appointment = _require_child(session, Appointment, person_id, appointment_id)
        commands.log_appointment_outcome(
            session,
            appointment,
            outcome=request.form.get("outcome", "").strip() or None,
            next_action=request.form.get("next_action", "").strip() or None,
        )
        session.commit()
        session.expire(target)
        return render_template("_person_main.html", **_person_context(target))


# --- CRUD ---------------------------------------------------------------
#
# Edit/delete actions for the person page and its children. All gated by
# ``login_required``; each runs one transaction then re-renders the
# ``_person_main`` fragment (deletes that remove the page itself redirect
# to the dashboard instead). ``_require_child`` enforces that the child row
# actually belongs to the person in the URL, so a guessed id can't reach
# another person's data.


def _require_child(session, model, person_id: int, obj_id: int):
    obj = session.get(model, obj_id)
    if obj is None or obj.person_id != person_id:
        abort(404)
    return obj


def _person_main(session, target):
    session.expire(target)
    return render_template("_person_main.html", **_person_context(target))


def _redirect(endpoint: str, **values):
    """htmx redirect (HX-Redirect on a 204) or a plain 302, by request type."""
    url = url_for(endpoint, **values)
    if request.headers.get("HX-Request"):
        resp = Response(status=204)
        resp.headers["HX-Redirect"] = url
        return resp
    return redirect(url)


def _form_role() -> Role:
    role_raw = request.form.get("role", "")
    if role_raw not in {r.value for r in Role}:
        abort(400)
    return Role(role_raw)


@bp.post("/person/new")
@auth.login_required
def add_person():
    name = request.form.get("name", "").strip()
    if not name:
        abort(400)
    with SessionLocal() as session:
        person = commands.add_person(
            session,
            name=name,
            role=_form_role(),
            date_of_birth=parse_date(request.form.get("date_of_birth")),
        )
        session.commit()
        person_id = person.id
    return _redirect("views.person", person_id=person_id)


@bp.post("/person/<int:person_id>/edit")
@auth.login_required
def edit_person(person_id: int):
    name = request.form.get("name", "").strip()
    if not name:
        abort(400)
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        commands.update_person(
            session,
            target,
            name=name,
            role=_form_role(),
            date_of_birth=parse_date(request.form.get("date_of_birth")),
            bsn=request.form.get("bsn", "").strip(),
            huisarts=request.form.get("huisarts", "").strip(),
            tandarts=request.form.get("tandarts", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/delete")
@auth.login_required
def delete_person(person_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        commands.delete(session, target)
        session.commit()
    return _redirect("views.dashboard")


@bp.post("/person/<int:person_id>/appointment/<int:appointment_id>/edit")
@auth.login_required
def edit_appointment(person_id: int, appointment_id: int):
    kind = request.form.get("kind", "").strip()
    if not kind:
        abort(400)
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        appointment = _require_child(session, Appointment, person_id, appointment_id)
        commands.update_appointment(
            session,
            appointment,
            kind=kind,
            scheduled_at=parse_datetime(request.form.get("scheduled_at")),
            status=AppointmentStatus(request.form.get("status", "due")),
        )
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/appointment/<int:appointment_id>/delete")
@auth.login_required
def delete_appointment(person_id: int, appointment_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        appointment = _require_child(session, Appointment, person_id, appointment_id)
        commands.delete(session, appointment)
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/obligation/<int:obligation_id>/edit")
@auth.login_required
def edit_obligation(person_id: int, obligation_id: int):
    kind = request.form.get("kind", "").strip()
    interval = request.form.get("interval_months", "").strip()
    if not kind or not interval.isdigit():
        abort(400)
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        obligation = _require_child(session, RecurringObligation, person_id, obligation_id)
        commands.update_obligation(
            session,
            obligation,
            kind=kind,
            interval_months=int(interval),
            last_done=parse_date(request.form.get("last_done")),
            active="active" in request.form,
        )
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/obligation/<int:obligation_id>/delete")
@auth.login_required
def delete_obligation(person_id: int, obligation_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        obligation = _require_child(session, RecurringObligation, person_id, obligation_id)
        commands.delete(session, obligation)
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/vaccination")
@auth.login_required
def add_vaccination(person_id: int):
    vaccine = request.form.get("vaccine", "").strip()
    if not vaccine:
        abort(400)
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        commands.add_vaccination(
            session,
            person_id,
            vaccine=vaccine,
            date=parse_date(request.form.get("date")),
            where=request.form.get("where", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/vaccination/<int:vaccination_id>/edit")
@auth.login_required
def edit_vaccination(person_id: int, vaccination_id: int):
    vaccine = request.form.get("vaccine", "").strip()
    if not vaccine:
        abort(400)
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        record = _require_child(session, VaccinationRecord, person_id, vaccination_id)
        commands.update_vaccination(
            session,
            record,
            vaccine=vaccine,
            date=parse_date(request.form.get("date")),
            where=request.form.get("where", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )
        session.commit()
        return _person_main(session, target)


@bp.post("/person/<int:person_id>/vaccination/<int:vaccination_id>/delete")
@auth.login_required
def delete_vaccination(person_id: int, vaccination_id: int):
    with SessionLocal() as session:
        target = _require_person(session, person_id)
        record = _require_child(session, VaccinationRecord, person_id, vaccination_id)
        commands.delete(session, record)
        session.commit()
        return _person_main(session, target)
