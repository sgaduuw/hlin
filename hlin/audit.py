"""Audit log: record who changed what, when.

One concern: the ``AuditAction`` vocabulary and the ``record()`` helper that
appends an ``AuditLog`` row to the request's session. Capture is *atomic*:
``record()`` does not commit, so the caller's transaction commits the change
and its audit row together and the trail has no silent gaps. It is called
from the view layer (routes / CLI), never from a model event or a lifecycle
hook, matching the sibling apps (mimir and bragi both capture audit with an
explicit call at the write site, not via ORM events).

The actor is read from the Flask session (set at login), guarded by
``has_request_context()`` so a CLI / system mutation records actor ``None``.
"""

from __future__ import annotations

from flask import has_request_context
from flask import session as flask_session
from sqlalchemy.orm import Session

from .models import AuditLog


class AuditAction:
    """Audit action vocabulary: ``domain.verb`` string constants. An open set
    (a new action needs no migration); naming a missing constant fails at
    import, which a bare string literal at the call site would not."""

    PERSON_CREATE = "person.create"
    PERSON_UPDATE = "person.update"
    PERSON_DELETE = "person.delete"
    APPOINTMENT_CREATE = "appointment.create"
    APPOINTMENT_UPDATE = "appointment.update"
    APPOINTMENT_LOG_OUTCOME = "appointment.log_outcome"
    APPOINTMENT_DELETE = "appointment.delete"
    OBLIGATION_CREATE = "obligation.create"
    OBLIGATION_UPDATE = "obligation.update"
    OBLIGATION_DELETE = "obligation.delete"
    VACCINATION_CREATE = "vaccination.create"
    VACCINATION_UPDATE = "vaccination.update"
    VACCINATION_DELETE = "vaccination.delete"
    CONTACT_CREATE = "contact.create"
    CONTACT_UPDATE = "contact.update"
    CONTACT_DELETE = "contact.delete"


# Every action value, for the audit page's filter dropdown.
ALL_ACTIONS: tuple[str, ...] = tuple(
    value
    for key, value in vars(AuditAction).items()
    if isinstance(value, str) and not key.startswith("_")
)


def _current_actor() -> tuple[int | None, str | None]:
    """``(user_id, username)`` of the logged-in actor, or ``(None, None)`` for
    an anonymous request or a CLI / system mutation (no request context)."""
    if not has_request_context():
        return None, None
    return flask_session.get("user_id"), flask_session.get("username")


def record(session: Session, action: str, target) -> None:
    """Append an audit row for ``action`` on ``target`` to ``session``.

    Does NOT commit: the caller's transaction commits the change and this row
    together (atomic, no silent gaps). ``target_type`` / ``target_id`` and the
    human ``summary`` are read off ``target``, so it must be alive and have a
    persistent id, call this BEFORE deleting it, and ``flush()`` a freshly
    created object first so its id is assigned. The actor is snapshotted from
    the session (username kept verbatim so the row survives login deletion).
    """
    actor_id, actor_username = _current_actor()
    session.add(
        AuditLog(
            action=action,
            actor_user_id=actor_id,
            actor_username=actor_username,
            target_type=target.__tablename__,
            target_id=target.id,
            summary=getattr(target, "audit_label", None),
        )
    )
