"""Audit log: record who changed what, when.

One concern: the ``AuditAction`` vocabulary and the ``record()`` helper that
appends an ``AuditLog`` row to the request's session. Capture is *atomic*:
``record()`` does not commit, so the caller's transaction commits the change
and its audit row together and the trail has no silent gaps. It is called
from the view layer (routes / CLI), never from a model event or a lifecycle
hook, matching the sibling apps (mimir and bragi both capture audit with an
explicit call at the write site, not via ORM events).

The actor is read from the Flask session (via ``auth``), guarded by
``has_request_context()`` so a CLI / system mutation records actor ``None``.
"""

from __future__ import annotations

import enum

from flask import has_request_context
from sqlalchemy.orm import Session

from . import auth
from .models import AuditLog


class AuditAction(enum.StrEnum):
    """Audit action vocabulary: ``domain.verb`` values. A ``StrEnum`` (the
    house idiom, like ``Role``) so members are usable as plain strings and the
    set iterates for the filter dropdown; naming a missing constant fails at
    import, which a bare string literal at the call site would not. The
    ``audit_log.action`` column stays a free ``String`` (open vocabulary: a new
    action needs no migration), this only supplies the typed constants."""

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
ALL_ACTIONS: tuple[AuditAction, ...] = tuple(AuditAction)


def record(session: Session, action: str, target) -> None:
    """Append an audit row for ``action`` on ``target`` to ``session``.

    Does NOT commit: the caller's transaction commits the change and this row
    together (atomic, no silent gaps). ``target_type`` / ``target_id`` and the
    human ``summary`` are read off ``target``, so it must be alive and have a
    persistent id, call this BEFORE deleting it, and ``flush()`` a freshly
    created object first so its id is assigned. The actor is snapshotted from
    the session (username kept verbatim so the row survives login deletion);
    a CLI / system mutation has no request context and records actor ``None``.
    """
    in_request = has_request_context()
    session.add(
        AuditLog(
            action=action,
            actor_user_id=auth.current_user_id() if in_request else None,
            actor_username=auth.current_username() if in_request else None,
            target_type=target.__tablename__,
            target_id=target.id,
            summary=getattr(target, "audit_label", None),
        )
    )
