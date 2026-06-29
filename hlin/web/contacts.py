"""Contacts directory: list the kids' social network and add to it.

Directory only, no care machinery (scope ceiling). Friends are grouped
under the child(ren) they belong to; parents/family/other get their own
section. Adding a friend can link it to one or more children and point at
an existing parent contact. To register a friend's parent, add a contact
of kind ``parent`` first, then it appears in the parent picker.
"""

from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from .. import auth, commands, store
from ..db import SessionLocal
from ..models import ContactKind
from ._forms import parse_date

bp = Blueprint("contacts", __name__, url_prefix="/contacts")


def _context(session) -> dict:
    return {
        "children": store.list_children(session),
        "other_contacts": store.non_friend_contacts(session),
        "parent_options": store.list_parent_contacts(session),
        "contact_kinds": [kind.value for kind in ContactKind],
    }


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
        parent_id = request.form.get("parent_contact_id", "").strip()
        commands.add_contact(
            session,
            name=name,
            kind=ContactKind(request.form.get("kind", "friend")),
            parent_contact_id=int(parent_id) if parent_id.isdigit() else None,
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            birthday=parse_date(request.form.get("birthday")),
            linked_person_ids=tuple(
                int(x) for x in request.form.getlist("linked_person_ids") if x.isdigit()
            ),
        )
        session.commit()
        return render_template("_contacts_main.html", **_context(session))
