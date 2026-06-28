# hlin

A small, self-hosted household information system: track appointments,
recurring obligations, and medical/admin history for the people a
household cares for (kids, the adults, their ageing parents), plus a
lightweight directory of the kids' social network. It feeds an existing
CalDAV setup with read-only `.ics` feeds rather than trying to be a
calendar client itself.

Named for **Hlín**, the Norse goddess who watches over the people Frigg
names so harm does not slip through.

> **Status: early WIP.** The data model, migrations, and household seed
> are in place. Recall logic, `.ics` feeds, the web UI, and the container
> packaging are not built yet.

## Stack

Python + Flask, SQLAlchemy 2.0 over SQLite (WAL), Alembic migrations,
pydantic-settings config, Jinja2 + htmx + Pico templates (no build step),
packaged with uv.

## Development

```sh
uv sync                              # install deps + project
uv run alembic upgrade head          # create / migrate the SQLite DB
uv run flask --app hlin seed         # seed the household (idempotent)
uv run flask --app hlin run          # dev server (http://127.0.0.1:5000)
uv run pytest                        # tests
uv run ruff check hlin tests         # lint
```

Edit `hlin/seed_data.py` to set your own household before seeding; the
placeholder names there are examples.

## Configuration

All config is environment-driven (prefix `HLIN_`), read at startup via
`hlin.settings.Settings`:

| Variable             | Default     | Purpose                                                        |
| -------------------- | ----------- | -------------------------------------------------------------- |
| `HLIN_DB_PATH`       | `hlin.db`   | On-disk SQLite path (the single backup target).                |
| `HLIN_HORIZON_DAYS`  | `60`        | Recall window for the "Coming up / Overdue" dashboard panel.   |
| `HLIN_SHARED_CREDENTIAL` | (unset) | Single shared household credential; unset == trust the network.|
| `HLIN_NTFY_URL`      | (unset)     | Optional ntfy base URL for the single outbound reminder channel.|
| `HLIN_NTFY_TOPIC`    | (unset)     | Optional ntfy topic.                                           |

## Backup

The SQLite file at `HLIN_DB_PATH` is the single source of truth. Take a
consistent snapshot for an external (e.g. Restic) job with the SQLite
backup API:

```sh
sqlite3 "$HLIN_DB_PATH" ".backup '/path/to/snapshot/hlin.db'"
```

Back up the snapshot, not the live file, so the copy is crash-consistent
even while the app is writing.
