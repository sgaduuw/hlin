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


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(user: User, password: str) -> bool:
    return check_password_hash(user.password_hash, password)


def log_in(user: User) -> None:
    session[_USER_ID] = user.id
    session[_USERNAME] = user.username


def log_out() -> None:
    session.pop(_USER_ID, None)
    session.pop(_USERNAME, None)


def current_username() -> str | None:
    return session.get(_USERNAME)


def is_authenticated() -> bool:
    return _USER_ID in session


def safe_next(target: str | None) -> str | None:
    """Only allow same-site relative redirect targets (no open redirect)."""
    if target and target.startswith("/") and not target.startswith("//"):
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
