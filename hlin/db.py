"""Engine and session factory.

SQLite specifics applied on every connect (mirrors the mimir / bragi
deployment shape): WAL journal mode (concurrent readers alongside a
writer), ``synchronous=NORMAL`` (the durable-and-fast pairing for WAL: a
process crash is safe, only an OS/power loss can drop the last commit),
``foreign_keys=ON`` (SQLite leaves FK enforcement off by default, which
would silently break our cascades), and a ``busy_timeout`` so a writer
waits briefly rather than erroring under the multi-worker gunicorn
deployment.

``SessionLocal`` uses ``autoflush=False`` (like the sibling apps): queries
do not implicitly flush pending writes first, so a write-then-query within
one session must ``flush()`` explicitly (e.g. ``seed_household`` flushes a
new person before it queries for its id). ``expire_on_commit=False`` keeps
committed objects usable while a request renders its response fragment.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .settings import settings


def make_engine(url: str) -> Engine:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(
    bind=engine, class_=Session, autoflush=False, expire_on_commit=False
)
