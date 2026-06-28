"""Web layer: HTML views and the read-only .ics feed routes.

``register(app)`` wires both blueprints onto the app; the package
re-exports nothing else, so the app factory only needs this one call.
"""

from __future__ import annotations

from flask import Flask

from . import feeds, views


def register(app: Flask) -> None:
    app.register_blueprint(views.bp)
    app.register_blueprint(feeds.bp)
