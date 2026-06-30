"""Contacts directory: list the kids' social network and add to it.

Directory only, no care machinery (scope ceiling). Friends are grouped
under the child(ren) they belong to; parents/family/other get their own
section. Adding a friend can link it to one or more children and point at
an existing parent contact. To register a friend's parent, add a contact
of kind ``parent`` first, then it appears in the parent picker.
"""

from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from .. import audit, auth, commands, store
from ..audit import AuditAction
from ..db import SessionLocal
from ..models import Contact, ContactKind
from ._forms import parse_date

bp = Blueprint("contacts", __name__, url_prefix="/contacts")


def _context(session) -> dict:
    return {
        "children": store.list_children(session),
        "other_contacts": store.non_friend_contacts(session),
        "parent_options": store.list_parent_contacts(session),
        "contact_kinds": [kind.value for kind in ContactKind],
    }


def _form_parent_id() -> int | None:
    parent_id = request.form.get("parent_contact_id", "").strip()
    return int(parent_id) if parent_id.isdigit() else None


def _form_linked_person_ids() -> tuple[int, ...]:
    return tuple(int(x) for x in request.form.getlist("linked_person_ids") if x.isdigit())


def _require_contact(session, contact_id: int) -> Contact:
    contact = session.get(Contact, contact_id)
    if contact is None:
        abort(404)
    return contact


@bp.get("/")
def index():
    with SessionLocal() as session:
        return render_template("contacts.html", **_context(session))


@bp.post("/")
@auth.login_required
def add():
    with SessionLocal() as session:
        name = request.form.get("name", "").strip()
        if not name:
            abort(400)
        contact = commands.add_contact(
            session,
            name=name,
            kind=ContactKind(request.form.get("kind", "friend")),
            parent_contact_id=_form_parent_id(),
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            birthday=parse_date(request.form.get("birthday")),
            linked_person_ids=_form_linked_person_ids(),
        )
        session.flush()  # assign the id before auditing the create
        audit.record(session, AuditAction.CONTACT_CREATE, contact)
        session.commit()
        return render_template("_contacts_main.html", **_context(session))


@bp.post("/<int:contact_id>/edit")
@auth.login_required
def edit(contact_id: int):
    with SessionLocal() as session:
        contact = _require_contact(session, contact_id)
        name = request.form.get("name", "").strip()
        if not name:
            abort(400)
        commands.update_contact(
            session,
            contact,
            name=name,
            kind=ContactKind(request.form.get("kind", "friend")),
            parent_contact_id=_form_parent_id(),
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            birthday=parse_date(request.form.get("birthday")),
            linked_person_ids=_form_linked_person_ids(),
        )
        audit.record(session, AuditAction.CONTACT_UPDATE, contact)
        session.commit()
        return render_template("_contacts_main.html", **_context(session))


@bp.post("/<int:contact_id>/delete")
@auth.login_required
def delete(contact_id: int):
    with SessionLocal() as session:
        contact = _require_contact(session, contact_id)
        audit.record(session, AuditAction.CONTACT_DELETE, contact)
        session.delete(contact)
        session.commit()
        return render_template("_contacts_main.html", **_context(session))
