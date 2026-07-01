# syntax=docker/dockerfile:1

# ---- builder: resolve deps + install the project into /app/.venv --------
FROM python:3.14-slim AS builder

# Pinned uv (bump in lockstep with the dev toolchain).
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first so this layer caches unless pyproject/uv.lock change.
# README.md is referenced by pyproject and needed when the project builds.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Then the application code and the project install itself.
COPY hlin ./hlin
COPY migrations ./migrations
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime ------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOME=/home/hlin \
    HLIN_DB_PATH=/data/hlin.db

WORKDIR /app

# Run as a non-root user; the SQLite file lives on the /data volume. Give the
# user a real, writable home: gunicorn's control server writes under $HOME, and
# a system account with an uncreated home makes it fail with EACCES on /home/hlin.
RUN useradd --system --uid 10001 --home-dir /home/hlin hlin \
    && mkdir -p /data /home/hlin \
    && chown hlin:hlin /data /home/hlin

COPY --from=builder --chown=hlin:hlin /app /app
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

USER hlin
VOLUME ["/data"]
EXPOSE 8000

# The entrypoint applies migrations, then execs the CMD (gunicorn).
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", \
     "--access-logfile", "-", "hlin:create_app()"]
