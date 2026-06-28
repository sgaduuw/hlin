# Changelog

All notable changes to hlin are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/sgaduuw/hlin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sgaduuw/hlin/releases/tag/v0.1.0
