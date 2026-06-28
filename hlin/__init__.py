"""hlin: self-hosted household care + contacts tracker."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from flask import Flask

from . import cli

try:
    __version__ = version("hlin")
except PackageNotFoundError:  # running from a source tree without install metadata
    __version__ = "0.0.0"


def create_app() -> Flask:
    app = Flask(__name__)
    # Keep rendered HTML tidy: strip the newline after a block tag and the
    # leading whitespace before one (spec UI requirement).
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    cli.register(app)

    @app.get("/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    return app
