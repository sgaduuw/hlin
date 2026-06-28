"""Flask CLI commands (``flask --app hlin <command>``)."""

from __future__ import annotations

import click
from flask import Flask
from flask.cli import with_appcontext

from .db import SessionLocal
from .seed_data import seed_household


def register(app: Flask) -> None:
    app.cli.add_command(seed_command)


@click.command("seed")
@with_appcontext
def seed_command() -> None:
    """Create the household persons and their initial recurring obligations."""
    with SessionLocal() as session:
        created = seed_household(session)
        session.commit()
    click.echo(f"Seeded {created} new record(s).")
