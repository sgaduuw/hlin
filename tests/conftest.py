"""Test fixtures.

NOTE: this uses an in-memory SQLite DB built straight from
``Base.metadata.create_all``, which is fast and isolated but cannot
reproduce file-backed cross-connection write-lock semantics (portfolio
calibration). It is adequate for model and pure-logic tests; anything that
depends on real write contention needs a file-backed fixture.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from hlin.models import Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # noqa: ANN001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with factory() as session:
        yield session
