#!/bin/sh
# Apply any pending schema migrations against the configured SQLite file,
# then hand off to the container command (gunicorn). Idempotent: a
# fully-migrated DB makes `alembic upgrade head` a no-op.
set -eu

alembic upgrade head

exec "$@"
