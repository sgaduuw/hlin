"""Audit log page: a read-only, login-gated view of who changed what.

The page reveals editor identities and the full change activity, so the
whole route is gated on login (anonymous viewers never see it), the same
posture as the redacted sensitive fields. Newest first, filterable by
action, with an id-cursor "load more".
"""

from __future__ import annotations

from flask import Blueprint, render_template, request

from .. import audit, auth, store
from ..db import SessionLocal

bp = Blueprint("audit", __name__, url_prefix="/audit")

_PAGE = 100


@bp.get("/")
@auth.login_required
def index():
    action = request.args.get("action") or None
    before_id = request.args.get("before", type=int)
    with SessionLocal() as session:
        # Fetch one extra to tell whether a further page exists.
        rows = store.list_audit(session, limit=_PAGE + 1, action=action, before_id=before_id)
        has_more = len(rows) > _PAGE
        entries = rows[:_PAGE]
        return render_template(
            "audit.html",
            entries=entries,
            actions=audit.ALL_ACTIONS,
            action=action,
            next_before=entries[-1].id if has_more and entries else None,
        )
