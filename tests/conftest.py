"""Test fixtures.

Two fixtures, by need:

* ``session`` - a fast in-memory SQLite session for pure model / recall /
  feed / command tests. It cannot reproduce file-backed cross-connection
  write-lock semantics (portfolio calibration); adequate for logic tests.
* ``client`` - a Flask test client backed by the app's own engine pointed
  at a temporary *file* DB (set before hlin is imported, below), with the
  schema created per test. Used for route / auth tests so they exercise the
  real app wiring and file-backed SQLite.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

# Must run before hlin is imported, so the app engine binds to a throwaway
# file DB instead of the developer's hlin.db.
_TMPDIR = tempfile.mkdtemp(prefix="hlin-tests-")
os.environ["HLIN_DB_PATH"] = str(pathlib.Path(_TMPDIR) / "test.db")
os.environ.setdefault("HLIN_SECRET_KEY", "testing-secret")

import pytest  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from hlin.models import Base  # noqa: E402


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


@pytest.fixture
def client():
    import hlin.db as db
    from hlin import create_app

    Base.metadata.create_all(db.engine)
    app = create_app()
    app.testing = True
    try:
        yield app.test_client()
    finally:
        Base.metadata.drop_all(db.engine)
