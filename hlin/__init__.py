"""hlin: self-hosted household care + contacts tracker."""

from __future__ import annotations

import os
import pathlib
import secrets
from importlib.metadata import PackageNotFoundError, version

from flask import Flask, redirect, request, url_for

from . import auth, cli, web
from .settings import settings

try:
    __version__ = version("hlin")
except PackageNotFoundError:  # running from a source tree without install metadata
    __version__ = "0.0.0"


def _resolve_secret_key() -> str:
    """A stable session signing key.

    Prefer the configured key. Otherwise persist a generated key in a file
    beside the database: gunicorn forks multiple workers that each build the
    app, so a per-process ephemeral key would make a cookie minted by one
    worker fail validation on another (the login feature then half-works).
    ``O_EXCL`` makes the first worker to create the file win; the rest read
    that value, so every worker and every restart converge on one key.
    """
    if settings.secret_key:
        return settings.secret_key
    key_path = pathlib.Path(settings.db_path).resolve().parent / ".hlin-secret-key"
    try:
        fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as handle:
            handle.write(secrets.token_hex(32))
    return key_path.read_text().strip()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = _resolve_secret_key()
    # Session cookie hardening: Lax SameSite blocks cross-site POST (CSRF
    # mitigation for the htmx form actions), HttpOnly is Flask's default, and
    # Secure is opt-in via settings so plain-HTTP dev still works.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = settings.session_cookie_secure
    # Keep rendered HTML tidy: strip the newline after a block tag and the
    # leading whitespace before one (spec UI requirement).
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    cli.register(app)
    web.register(app)

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        # Available to every template: footer version, dashboard horizon, and
        # the auth state that gates edit affordances and redacts sensitive
        # fields for anonymous viewers.
        return {
            "version": __version__,
            "horizon_days": settings.horizon_days,
            "logged_in": auth.is_authenticated(),
            "current_user": auth.current_username(),
        }

    @app.before_request
    def enforce_require_login():
        # Optional full lockdown: when HLIN_REQUIRE_LOGIN is set, reads need a
        # login too. Off by default (reads open, sensitive fields redacted).
        if not settings.require_login or auth.is_authenticated():
            return None
        allowed = {"auth.login", "auth.login_submit", "static", "healthz"}
        if request.endpoint in allowed:
            return None
        return redirect(url_for("auth.login", next=request.path))

    @app.get("/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    return app
