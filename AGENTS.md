# AGENTS.md

Conventions for AI coding agents working on hlin. Tracked in the repo
deliberately: more than one agent and more than one tool may work on
this codebase, and a convention nobody can read is a convention
nobody follows. Read this before your first change.

This file says *what to do*. Its companion [`CONTEXT.md`](CONTEXT.md),
beside it at the repo root, says *why*: the domain split, the access
model, and the decisions that look odd until you know what they cost.
Where a rule here has a one-line justification, the full reasoning is
usually there.

Operator and deployment specifics (host access, deploy mechanics, the
release walkthrough) are not in the repo. If a task needs them, say so
and ask rather than guessing.

## What hlin is

A self-hosted household care and contacts tracker: appointments,
recurring obligations, and medical/admin history for the people a
household cares for (children, the adults, their ageing parents), plus
a lightweight directory of the children's social network, exposed to an
existing CalDAV setup as read-only `.ics` feeds.

It is a single-household system for read-mostly visibility. It feeds an
existing calendar rather than replacing it.

## The rule that matters most

**hlin stores BSNs and informal medical notes about minors and elderly
people.** Reads are open by default so the household can glance at the
schedule without logging in, which means the redaction boundary is
load-bearing rather than cosmetic.

So: **when you add or reclassify a sensitive field, audit every
anonymous read surface, not just the HTML templates.** The `.ics` feeds
are anonymous-readable, as is any future export or API. Template-only
redaction leaks straight out of the feed, which is not hypothetical:
the 0.2.0 review caught exactly that, with the appointment outcome
embedded in the calendar event description while the templates
correctly hid it.

Currently gated on `logged_in`: BSN, person notes, appointment
outcome and next action, vaccinations. `HLIN_REQUIRE_LOGIN` flips the
whole app to full lockdown when a deploy wants it.

## Stack

Deliberately the same stack as the sibling project mimir: Python and
Flask, SQLAlchemy 2.0 over SQLite (WAL and `foreign_keys=ON` on every
connect), Alembic migrations, pydantic-settings config, Jinja2 with
htmx and Pico (no build step), gunicorn in the container, uv for
packaging. Python `>=3.14`, regular rather than free-threaded: the app
is process-worker Flask with no threading pressure, so 3.14t buys
nothing here.

## Commands

```sh
uv sync
uv run pytest
uv run ruff check hlin tests
uv run ruff format --check hlin tests
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "<msg>"
uv run flask --app hlin run        # dev server
uv run flask --app hlin seed       # idempotent household seed
uv run flask --app hlin remind     # ntfy reminder; --dry-run to preview
```

**Apply the formatter, do not just check it.** Run
`uv run ruff format hlin tests` before pushing rather than trusting
`--check`. A local `--check` has twice reported clean on a file CI's
same-version ruff then reformatted, so applying leaves the tree
canonical regardless and saves the red-CI round trip. Run `uv sync`
first so the local ruff matches the lockfile.

**Container builds do not happen locally.** There is no docker or
podman on the development machine, so the Dockerfile is validated by
CI on every PR. Do not propose a local build as a verification step.

## Where code goes

One concern per file: a reader should be able to name each module's job
in a sentence. hlin is small, so the core is flat single-concern
modules plus one `web/` package. Promote a module to a package (with
`__init__.py` re-exporting the public surface) only once its job needs
an "and", never pre-emptively.

Core (`hlin/`):

- `models.py` SQLAlchemy 2.0 tables (`Mapped`/`mapped_column`, the enums).
- `db.py` engine, `SessionLocal`, the on-connect PRAGMA handler.
- `settings.py` the env-driven `Settings` (pydantic-settings, prefix `HLIN_`).
- `store.py` **read** queries (the SELECT side); pure, takes a `Session`.
- `commands.py` **write** operations; takes a `Session` and leaves the
  commit to the caller (one connection and transaction per request).
- `recall.py` next-due dates and dashboard recall classification (pure).
- `feeds.py` iCalendar builders (pure: data in, `Calendar` out).
- `ics.py` parse an uploaded `.ics` invite into appointment fields. The
  whole parse is guarded so bad input raises `InvalidICS`, never a 500.
- `notify.py` optional ntfy reminder (stdlib urllib, no `requests`).
- `auth.py` password hashing, session login state, `login_required`, `safe_next`.
- `audit.py` the audit-log recorder: `AuditAction` vocabulary and `record()`.
- `seed_data.py` first-run household seed.
- `cli.py` `flask` CLI commands.
- `__init__.py` the `create_app()` factory (wiring only).

Web (`hlin/web/`): `views.py` (dashboard, person page, person write
actions), `contacts.py`, `feeds.py`, `auth.py` (login and logout
routes), `audit.py` (the login-gated `/audit` page), `_forms.py`
(shared form-field parsers; the underscore means infrastructure, not
public surface), `__init__.py` (`register(app)` wires the blueprints).

Templates (`hlin/templates/`): page templates extend `base.html`. The
`_<area>_main.html` partials are the htmx swap targets, and a page
template is a thin `{% include %}` wrapper over its `_main` partial.

Static (`hlin/static/`): vendored `pico.min.css` and `htmx.min.js`,
plus `drop.js` (the `.ics` drop zone). Its handlers are
document-delegated so they survive htmx fragment swaps; any future
JavaScript follows the same shape: small, no build step, delegated for
swap-survival, with a no-JS fallback.

By kind:

- New table or column: `models.py` plus an alembic revision.
- New read query: `store.py`. New write or mutation: `commands.py`.
- New route: the matching `web/<area>.py` blueprint. A new area means a
  new module there, registered in `web/__init__.py`.
- New tunable: a `Settings` field with a default and an env override,
  read as `settings.foo`, never `os.environ` at the call site.
- New CLI command: `cli.py`. A new self-contained concern gets its own
  top-level module.
- New behaviour: add a test (`tests/test_<module>.py`) rather than
  relying on a manual check.

## Conventions that are load-bearing

- **Audit every mutation.** Capture is explicit rather than an ORM
  event, so **a new mutating route must add an `audit.record(session,
  AuditAction.X, target)` call**; there is no automatic safety net. For
  a create, `session.flush()` to assign the id, then `record`, then
  `commit`. For an edit, `record` then `commit`. For a delete, `record`
  **before** `session.delete()`, while the row is still alive. It
  writes on the request session, so the change and its audit row commit
  atomically. Add an `AuditAction` constant for the new action.
- **Every mutation is `@auth.login_required`**, and child-row routes
  call `_require_child` to verify ownership against the person in the
  URL. Reads are open by default; see the redaction rule above.
- **Validate form input to a 400, never a 500.** A crafted POST must
  not `ValueError` its way to a 500. Use
  `web/_forms.enum_field(cls, raw, default=...)` for `<select>` values
  (blank gives the default, invalid aborts 400), and the tolerant
  `parse_date` / `parse_datetime` (malformed gives `None`). Bound free
  numerics and guard them with `x.isascii() and x.isdigit()` before
  `int()`, because `isdigit()` alone accepts unicode digits that
  `int()` rejects. Follow `_form_role`'s validate-or-400 shape.
  Watch derived values feeding an always-open surface: an unbounded
  obligation interval once overflowed the next-due date and 500'd the
  anonymous dashboard and feeds.
- **Config is env-driven** through `hlin.settings.Settings` (prefix
  `HLIN_`). Callers read `settings.foo`.
- **`Appointment.kind` and `RecurringObligation.kind` are a loose
  free-string vocabulary** (`APPOINTMENT_KINDS` only suggests values to
  the UI). `role`, appointment `status`, and contact `kind` ARE
  constrained (VARCHAR plus CHECK) enums. The reasoning is in
  CONTEXT.md; do not tighten the loose ones without reading it.
- **Scope ceiling: persons get full care machinery, contacts get a
  directory entry and a birthday.** Never add appointments,
  obligations, or feeds to contacts. If a contact needs those, it
  should be a `Person`. This is the project's ceiling, not a waypoint.
- **No em-dashes or double-dashes in prose**, anywhere: comments,
  docstrings, commit messages, PR bodies, CHANGELOG. Use commas,
  colons, parentheses, or restructure.

## Tests

`uv run pytest` is the primary gate. Add a test for new behaviour
rather than relying on a manual check, especially for the redaction
boundary, the audit calls, and form validation, since a regression
there is silent.

Note the test fixtures use in-memory SQLite, which cannot reproduce
cross-connection write-lock semantics or anything that needs two
requests in flight at once. The dev server is single-process for the
same reason. If a change depends on multi-worker behaviour, reason
about it explicitly; localhost will not show it.

## CHANGELOG

**Add a line under `## [Unreleased]` in the same PR as the change**,
for any user-visible behaviour, schema, config, or CLI/route shape
change. Skip it only for pure internal refactors. Entries become the
published release notes an operator sizes a deploy from.

Categories: **Added**, **Changed**, **Deprecated**, **Removed**,
**Fixed**, **Security**.

## README currency

Before opening a PR, sweep the README for anything the change
invalidates: command examples, env vars and flag names, route lists,
project-layout listings, status and feature claims, hardcoded versions.
Removing or renaming a structural identifier (a module, a Settings
field, a CLI command) means grepping the README for the old name in the
same PR.

## Pull requests

- **One closing keyword per issue.** `Closes #N, #M.` closes only `#N`
  and silently leaves `#M` open. Write `Closes #N. Closes #M.` and put
  the list in the PR body.
- Keep the diff truthful to its title. If unrelated drift appears in
  the working tree, revert it rather than bundling it.

## Branching, versioning, CI

git-flow. `develop` is the GitHub default branch and the integration
target; `main` holds tagged released code. Feature work branches off
`develop`; releases go through `release/X.Y.Z`; urgent fixes through
`hotfix/X.Y.Z` off `main`.

The version source of truth is `pyproject.toml`'s `version`, exposed as
`hlin.__version__` via `importlib.metadata`. `uv.lock` is refreshed in
the same commit. Both are bumped on the release branch, not on feature
branches. SemVer by what changed: PATCH for fixes and dependency
refreshes, MINOR for behaviour, UX, or new config, MAJOR for schema or
interface breaks.

CI is the gate on pull requests. `ci.yml` runs `lint-and-test` (ruff
check, ruff format check, pytest on Python 3.14 via uv), `hadolint`,
and `docker-build`, which builds the image without pushing so the
Dockerfile is validated on every PR (it cannot be built locally).
`build-image.yml` fires on a `v*` tag push and only builds and pushes
the image, with no test re-run: it trusts the green PR the tag sits on.
`main` has required checks; `develop` is loose.

## If you are unsure

Ask rather than guess, particularly about anything touching the
redaction boundary for sensitive fields, the audit trail's
completeness, or the persons-versus-contacts scope ceiling.
