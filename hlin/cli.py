"""Flask CLI commands (``flask --app hlin <command>``)."""

from __future__ import annotations

from datetime import date
from urllib.error import URLError

import click
from flask import Flask
from flask.cli import with_appcontext

from . import notify, store
from .db import SessionLocal
from .recall import obligations_needing_attention
from .seed_data import seed_household
from .settings import settings


def register(app: Flask) -> None:
    app.cli.add_command(seed_command)
    app.cli.add_command(remind_command)


@click.command("seed")
@with_appcontext
def seed_command() -> None:
    """Create the household persons and their initial recurring obligations."""
    with SessionLocal() as session:
        created = seed_household(session)
        session.commit()
    click.echo(f"Seeded {created} new record(s).")


@click.command("remind")
@click.option("--dry-run", is_flag=True, help="Print the reminder instead of sending it.")
@with_appcontext
def remind_command(dry_run: bool) -> None:
    """Send a reminder of overdue / due-soon obligations to ntfy.

    No in-app scheduler: run this from cron or a systemd timer.
    """
    with SessionLocal() as session:
        items = obligations_needing_attention(
            store.active_obligations(session),
            store.booked_appointments(session),
            today=date.today(),
            horizon_days=settings.horizon_days,
        )
        message = notify.build_reminder(items)
        if message is None:
            click.echo("Nothing due; no reminder sent.")
            return
        configured = bool(settings.ntfy_url and settings.ntfy_topic)
        if dry_run or not configured:
            if not configured:
                click.echo("ntfy not configured; printing instead:")
            click.echo(message)
            return
        try:
            notify.send_ntfy(settings, message)
        except URLError as exc:
            raise click.ClickException(f"ntfy POST failed: {exc}") from exc
        click.echo(f"Sent reminder ({len(items)} item(s)) to ntfy.")
