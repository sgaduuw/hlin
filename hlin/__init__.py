"""hlin: self-hosted household care + contacts tracker."""

from __future__ import annotations

import secrets
from importlib.metadata import PackageNotFoundError, version

from flask import Flask, redirect, request, url_for

from . import auth, cli, web
from .settings import settings

try:
    __version__ = version("hlin")
except PackageNotFoundError:  # running from a source tree without install metadata
    __version__ = "0.0.0"


def create_app() -> Flask:
    app = Flask(__name__)
    # A configured key keeps sessions valid across restarts; absent one, an
    # ephemeral per-process key is fine for dev (logs everyone out on boot).
    app.secret_key = settings.secret_key or secrets.token_hex(32)
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
