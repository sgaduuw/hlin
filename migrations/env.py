"""Alembic environment.

The DB URL and metadata come from the application (``hlin.db.engine`` and
``hlin.models.Base``) so migrations always target the same SQLite file the
app uses, configured from ``HLIN_DB_PATH``. ``render_as_batch`` is on so
SQLite ALTERs work for future migrations; ``compare_type`` catches column
type drift on autogenerate.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from hlin.db import engine
from hlin.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
