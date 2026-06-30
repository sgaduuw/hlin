# hlin

A small, self-hosted household information system: track appointments,
recurring obligations, and medical/admin history for the people a
household cares for (kids, the adults, their ageing parents), plus a
lightweight directory of the kids' social network. It feeds an existing
CalDAV setup with read-only `.ics` feeds rather than trying to be a
calendar client itself.

Named for **Hlín**, the Norse goddess who watches over the people Frigg
names so harm does not slip through.

> **Status: v1 scope complete, plus inline admin.** In place: the data
> model, migrations, household seed, recall logic, read-only `.ics` feeds,
> the dashboard and per-person pages, the quick-add / logging write flow
> (add appointment, add obligation, log an outcome which advances the
> matching obligation), full inline CRUD on persons, appointments,
> obligations, vaccinations and contacts behind multi-user login, an
> append-only activity log and optional login-to-person links, the
> contacts directory, the optional ntfy reminder, and container packaging
> (Dockerfile + Compose).

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
uv run flask --app hlin remind --dry-run   # preview the ntfy reminder
uv run pytest                        # tests
uv run ruff check hlin tests         # lint
```

Edit `hlin/seed_data.py` to set your own household before seeding; the
placeholder names there are examples.

## Calendar feeds

Read-only iCalendar feeds, subscribe to them in your calendar client (they
are not a writable CalDAV server). Booked appointments are timed events,
derived obligation due-dates are all-day events, and contact birthdays are
yearly all-day events. UIDs are stable so clients update events in place.

| Feed                      | Contents                                          |
| ------------------------- | ------------------------------------------------- |
| `/feeds/all.ics`          | All persons' appointments and obligation due-dates.|
| `/feeds/person/<id>.ics`  | One person's appointments and due-dates.          |
| `/feeds/social.ics`       | Contact birthdays.                                |

The dashboard and each person page link to the relevant feed URLs.

## Configuration

All config is environment-driven (prefix `HLIN_`), read at startup via
`hlin.settings.Settings`:

| Variable             | Default     | Purpose                                                        |
| -------------------- | ----------- | -------------------------------------------------------------- |
| `HLIN_DB_PATH`       | `hlin.db`   | On-disk SQLite path (the single backup target).                |
| `HLIN_HORIZON_DAYS`  | `60`        | Recall window for the "Coming up / Overdue" dashboard panel.   |
| `HLIN_SECRET_KEY`    | (unset)     | Flask session signing key. If unset, a key is generated once and persisted as `.hlin-secret-key` beside the database, stable across gunicorn workers and restarts. Set it explicitly to keep the key out of the data volume or share it across hosts.|
| `HLIN_SESSION_COOKIE_SECURE` | `false` | Mark the session cookie `Secure` (sent only over HTTPS). Leave off for plain-HTTP dev; set true in production, where TLS terminates at the reverse proxy.|
| `HLIN_REQUIRE_LOGIN` | `false`     | When true, even reads require login (full lockdown). Off by default: reads are open and only sensitive fields are redacted for anonymous viewers.|
| `HLIN_NTFY_URL`      | (unset)     | Optional ntfy base URL for the single outbound reminder channel.|
| `HLIN_NTFY_TOPIC`    | (unset)     | Optional ntfy topic.                                           |

## Authentication

hlin distinguishes anonymous viewers from logged-in editors. Reads are open
by default (the dashboard, person pages and the schedule), but **every
mutation requires login**, and sensitive fields (BSN, medical/admin notes,
appointment outcomes and follow-ups, vaccination records) are redacted for
anonymous viewers. Set `HLIN_REQUIRE_LOGIN=true` to also gate reads.

Accounts are minimal: a username and a password hash, no roles, no
self-registration. A login may optionally be linked to a tracked person
("this login is me"); when linked, the nav links your name to your person
page. Manage accounts and links from the CLI:

```sh
uv run flask --app hlin user add linda            # prompts for a password
uv run flask --app hlin user add linda --person 3 # ... and link to person id 3
uv run flask --app hlin user link linda 3         # link an existing account
uv run flask --app hlin user unlink linda         # remove the link
uv run flask --app hlin user list                 # accounts and their linked person
uv run flask --app hlin user remove linda
```

Containerised, the same commands run via `docker compose exec`:

```sh
docker compose exec hlin flask --app hlin user add linda
```

Login sessions survive restarts out of the box (the signing key is persisted
beside the database). Set `HLIN_SECRET_KEY` explicitly if you would rather
keep the key out of the data volume, and `HLIN_SESSION_COOKIE_SECURE=true`
behind your HTTPS reverse proxy.

### Activity log

Every change (add / edit / delete of a person, appointment, obligation,
vaccination, or contact) is recorded in an append-only audit log, written
atomically with the change. Logged-in users can review it at `/audit`
(newest first, filterable by action); it shows who did what and when. The
activity log is never shown to anonymous viewers.

## Reminders (optional)

`hlin` can POST a summary of overdue / due-soon obligations to an
[ntfy](https://ntfy.sh) topic. There is no in-app scheduler, run the
command from cron or a systemd timer:

```sh
uv run flask --app hlin remind            # send if HLIN_NTFY_* are set
uv run flask --app hlin remind --dry-run  # print the message instead
```

Set `HLIN_NTFY_URL` (the ntfy base URL) and `HLIN_NTFY_TOPIC`. With nothing
due, no notification is sent. With ntfy unset, the command prints the
message instead of sending.

> The reminder contains household names and appointment kinds. Point ntfy
> at a self-hosted server or an unguessable, access-controlled topic, not a
> public `ntfy.sh` topic.

## Deployment

Ships as a single container. The image runs gunicorn on port 8000 as a
non-root user and keeps the SQLite database on a `/data` volume. On every
start the entrypoint applies pending migrations (`alembic upgrade head`),
so a fresh volume is initialised automatically.

```sh
docker compose up -d --build
docker compose exec hlin flask --app hlin seed            # once, after first start
docker compose exec hlin flask --app hlin user add linda  # create a login account
```

TLS is assumed to terminate upstream at your reverse proxy; the container
serves plain HTTP on the trusted network. Point the proxy at port 8000 (or
bind it to localhost in `docker-compose.yml` if the proxy shares the host).

Send reminders on a schedule from the host's cron or a systemd timer:

```sh
docker compose exec -T hlin flask --app hlin remind
```

Configure via the environment variables documented above, set in
`docker-compose.yml` or an `.env` file Compose reads.

## Backup

The SQLite file at `HLIN_DB_PATH` is the single source of truth. Take a
*consistent* snapshot (not a copy of the live file, which may be mid-write)
with the SQLite backup API, then let an external Restic job pick up the
snapshot.

Containerised (the slim image has Python, not the `sqlite3` CLI):

```sh
docker compose exec -T hlin python - <<'PY'
import sqlite3
src = sqlite3.connect("/data/hlin.db")
dst = sqlite3.connect("/data/hlin-backup.db")
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
```

Local / dev, with the `sqlite3` CLI:

```sh
sqlite3 "$HLIN_DB_PATH" ".backup hlin-backup.db"
```

Point Restic at the resulting `hlin-backup.db` (inside the `hlin-data`
volume), not the live database.
