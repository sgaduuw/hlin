"""Engine and session factory.

SQLite specifics applied on every connect: WAL journal mode (concurrent
readers alongside a writer), ``foreign_keys=ON`` (SQLite leaves FK
enforcement off by default, which would silently break our cascades), and
a ``busy_timeout`` so a writer waits briefly rather than erroring under the
multi-worker gunicorn deployment. This mirrors the mimir deployment shape.
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
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
