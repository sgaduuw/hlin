# Changelog

All notable changes to hlin are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Audit log: an append-only record of who changed what, written atomically
  with each change (no silent gaps). A new `/audit` activity page (logged-in
  only), newest first, filterable by action. Anonymous viewers never see it.
- Optional login-to-person link: a login MAY be linked to a tracked person
  ("this login is me"), managed via `flask --app hlin user add --person`,
  `user link`, and `user unlink` (`user list` shows the link). When linked,
  the nav links the logged-in name to that person's page.

### Changed
- SQLite connections now also set `PRAGMA synchronous=NORMAL` (the
  durable-and-fast pairing for WAL), and the session factory uses
  `autoflush=False`, aligning hlin's DB layer with the sibling apps
  (mimir / bragi). No behaviour change for users.

## [0.2.0] - 2026-06-29

Adds web-based administration so the household can manage everything from the
UI, not just the CLI, with editing gated behind login.

### Added
- Multi-user login (minimal: username + werkzeug password hash, no roles,
  no self-registration), managed via the `flask --app hlin user`
  add/list/remove commands. New settings: `HLIN_SECRET_KEY` (session
  signing; persisted beside the database when unset, stable across gunicorn
  workers), `HLIN_SESSION_COOKIE_SECURE` (mark the cookie Secure behind an
  HTTPS proxy), and `HLIN_REQUIRE_LOGIN` (gate reads too).
- Full inline CRUD behind login: add/edit/delete persons, appointments,
  obligations (with an active toggle), vaccinations, and contacts, edited
  in place via htmx fragments on the existing pages. Child rows are
  ownership-checked against the person in the URL.

### Changed
- Reads stay open by default, but sensitive fields (BSN, medical/admin
  notes, appointment outcomes and follow-ups, vaccination records) are now
  redacted for anonymous viewers; the schedule itself stays visible. Every
  mutation requires login. Supersedes the spec's single-shared-credential
  constraint.

### Security
- The anonymous `.ics` feeds no longer embed the appointment outcome in the
  event description (present since 0.1.0); the outcome is a
  redacted-for-anonymous field. The login redirect target is hardened
  against backslash / control-character open-redirect bypasses, the session
  cookie is `SameSite=Lax`, and an unknown username runs a dummy password
  compare to avoid a timing oracle.

## [0.1.0] - 2026-06-29

First release: a self-hosted household care and contacts tracker that feeds
an existing CalDAV setup rather than replacing it.

### Added
- Data model (SQLAlchemy 2.0 + Alembic over SQLite, WAL): tracked persons
  (child / adult / elder) with appointments, recurring obligations, and
  vaccination records; a contacts directory (friends linked many-to-many to
  children, a friend's parent stored once as a self-referenced contact).
- Recall logic: derived next-due dates (`last_done + interval_months`, never
  stored), horizon classification (overdue / due-soon), and the dashboard
  "Coming up / Overdue" panel (overdue first, earliest-due first).
- Read-only iCalendar feeds (`/feeds/all.ics`, `/feeds/person/<id>.ics`,
  `/feeds/social.ics`): booked appointments as timed events, obligation
  due-dates as all-day events, contact birthdays as yearly all-day events,
  with stable UIDs and DTSTAMP.
- Server-rendered UI (Flask + Jinja + htmx + Pico, no build step): the
  dashboard, per-person page, and contacts directory, plus a quick-add /
  logging flow where logging an appointment outcome advances the matching
  recurring obligation.
- Optional outbound reminders to ntfy via the `flask --app hlin remind`
  command (no in-app scheduler; run from cron or a systemd timer).
- Household seed (`flask --app hlin seed`, idempotent) and a `/healthz`
  endpoint.
- Container packaging: multi-stage uv build, gunicorn, the SQLite file on a
  `/data` volume, migrations applied on startup. Python 3.14.
- Tier-C CI: PR-gated lint / format / tests / hadolint / image build, and a
  tag-triggered image publish to GHCR.

[Unreleased]: https://github.com/sgaduuw/hlin/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/sgaduuw/hlin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sgaduuw/hlin/releases/tag/v0.1.0
