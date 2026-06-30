"""Multi-user authentication.

Minimal: password hashing (werkzeug, ships with Flask), session-based login
state, and a ``login_required`` guard. No roles (every logged-in user is a
full editor) and no self-registration (accounts come from the ``flask user``
CLI). Reads are open; mutations are gated.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from flask import Response, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .models import User

_USER_ID = "user_id"
_USERNAME = "username"
_PERSON_ID = "person_id"  # the tracked Person this login is linked to, if any

# Compared against when the username is unknown, so an absent user costs the
# same pbkdf2 work as a wrong password and the two are not distinguishable by
# response latency (no username-enumeration oracle).
_DUMMY_HASH = generate_password_hash("hlin-no-such-user")


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(user: User | None, password: str) -> bool:
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return check_password_hash(user.password_hash, password)


def log_in(user: User) -> None:
    session[_USER_ID] = user.id
    session[_USERNAME] = user.username
    session[_PERSON_ID] = user.person_id


def log_out() -> None:
    session.pop(_USER_ID, None)
    session.pop(_USERNAME, None)
    session.pop(_PERSON_ID, None)


def current_username() -> str | None:
    return session.get(_USERNAME)


def current_user_id() -> int | None:
    return session.get(_USER_ID)


def current_person_id() -> int | None:
    """The tracked Person this login is linked to, or None. Captured at login;
    a link change takes effect on the next login (no per-request DB lookup)."""
    return session.get(_PERSON_ID)


def is_authenticated() -> bool:
    return _USER_ID in session


def safe_next(target: str | None) -> str | None:
    """Only allow same-site relative redirect targets (no open redirect).

    A leading ``/`` is necessary but not sufficient: ``//host`` is
    protocol-relative, and ``/\\host`` reaches the same place because
    Werkzeug emits the backslash verbatim and browsers normalise ``\\`` to
    ``/``. Reject backslashes, control characters, and any surrounding
    whitespace, then require a single leading slash.
    """
    if not target or target != target.strip():
        return None
    if "\\" in target or any(ord(c) < 0x20 for c in target):
        return None
    if target.startswith("/") and not target.startswith("//"):
        return target
    return None


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            if request.headers.get("HX-Request"):
                # Tell htmx to navigate the browser to the login page.
                response = Response(status=401)
                response.headers["HX-Redirect"] = url_for("auth.login")
                return response
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped
