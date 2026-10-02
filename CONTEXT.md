# CONTEXT.md

Design rationale for hlin. [`AGENTS.md`](AGENTS.md) says what to do;
this file says why, and is the companion to read before making a
non-trivial change.

**Tracked in the repo since 2026-10-02.** It was gitignored until
then, on the reasoning that the documentation trio is workspace state.
That reasoning holds for personal memories and for the operator
surface, and is wrong for design rationale, which a contributor needs
in order to extend a rule rather than only obey it. Sibling project
mimir learned the cost directly: its most recurring defect class was
documented only in a gitignored file, and an agent that could not read
it shipped two fresh instances in one release.

Two consequences of being public:

- **No operator surface here.** Deployment specifics and the release
  walkthrough live in the untracked `_claude/CLAUDE.md`.
- **Some pointers lead outside the repo.** References to `MEMORY.md`
  and `_claude/specs/` point at local, untracked working notes, kept
  because they are accurate provenance. If you are reading from a
  clone and cannot find one, you are not missing a rule, only the
  story behind it.

**This file names the categories of sensitive data hlin holds (BSNs,
medical notes) because the access model cannot be explained without
them. It contains no actual personal data, and must not acquire any.**
Use invented examples, never a real person's details, and not only
because the data is sensitive: an example that is real is exactly the
harm the redaction posture below exists to prevent.

## What hlin is

A single-household information system for *read-mostly visibility* of the
state of the people a household cares for, feeding an existing CalDAV
setup rather than replacing it. It grew out of a "Kids Tracker" brief on
2026-06-28 and was widened in the same brainstorm to cover all tracked
persons and the kids' social network. The guiding value is that the state
of the household's people is visible rather than held in someone's head,
and that adding to it takes seconds.

## Why two entity families (persons vs contacts)

The brainstorm split the domain in two deliberately:

- **Tracked persons** (kids, the household adults, their parents) get the
  full care machinery: appointments, recurring obligations, vaccination
  records, recall logic, per-person `.ics` feeds. These are the people
  whose state the household actively *manages*.
- **Contacts** (the kids' friends and those friends' parents) get a
  directory entry and a birthday, nothing more. These are people the
  household needs to *remember*, not manage.

Collapsing contacts into `Person` was rejected: it would imply friends
have appointments/obligations/feeds (inviting the exact scope creep the
brief warns against) and produce a polymorphic table with a muddled "add
person -> which kind?" UI. The manage-vs-remember line is what keeps the
social half from sprawling, and it is the project's scope *ceiling*, not a
waypoint.

## Why Person generalises Child

Tracking the adults and grandparents is the *same concern* as tracking
the kids (appointments, cadenced obligations, medical notes), and elder
care exercises the recall logic harder than kids do. So `Child` became
`Person` with a `role` field (`child | adult | elder`) that is
display/grouping only and load-bearing for no logic: one cared-for
entity, not two near-identical ones.

## Why Flask, not FastAPI

The brief defaulted to FastAPI; the brainstorm switched to Flask. hlin is
a server-rendered Jinja + htmx HTML app with no JSON API surface, no
streaming, and trivial concurrency, so FastAPI's async /
pydantic-request-validation / OpenAPI value props never fire and its
async story only adds friction against a sync SQLAlchemy session. Flask
matches mimir exactly, so every portfolio convention and hard-won gotcha
(gunicorn-tier logging, multi-worker SQLite write-lock contention, the
`:memory:` test-fixture blind spot, WAL-on-connect) transfers directly.
hlin is "another mimir-shaped app" on purpose.

## Why kind is a loose vocabulary

`Appointment.kind` / `RecurringObligation.kind` are free strings, not a
DB-constrained enum, because the set of appointment types is open-ended
(a new specialist, a one-off admin errand) and forcing a migration to add
one is friction the household scale does not warrant. `role`, appointment
`status`, and contact `kind` are small, stable, state-machine-ish sets,
so those stay constrained (VARCHAR + CHECK) enums.

## Why the name

Hlín is the Norse goddess who watches over the people Frigg names so harm
does not slip through: the app's job is to watch the household's
obligations so nothing slips. Fits the portfolio's evocative-not-literal
naming convention (mimir = memory, bragi = poetry).

## Why multi-user login, reads-open with field-level redaction

The original spec (constraint #6) said "single shared household login,
do not build user accounts." 0.2.0 superseded that with **minimal
multi-user accounts** (username + werkzeug password hash, no roles, no
OAuth, no self-registration, managed via `flask user`). The driver was
wanting a partner to feel comfortable editing: distinct accounts beat a
shared password for that, at trivial extra cost (one table, one CLI
group). The constraint's real intent (no role machinery, no OAuth, not
multi-tenant) still holds; only the *single*-credential part was lifted.

The access model is **reads-open by default, mutations always gated, and
sensitive fields redacted for anonymous viewers** rather than all-or-
nothing auth. The household value is *visibility* (the dashboard and
schedule should be glanceable without a login), but the store holds
BSNs and informal medical notes for minors and elders, which must not be
world-readable. So the schedule (who/what/when) stays anonymous-visible
while BSN, medical/admin notes, appointment outcomes/follow-ups, and
vaccinations are gated on `logged_in`. `HLIN_REQUIRE_LOGIN` flips it to
full lockdown when the deploy wants it.

Corollary learned the hard way (caught in the 0.2.0 whole-diff review):
**a redaction policy has to cover every anonymous *read surface*, not
just the HTML templates.** The `.ics` feeds are anonymous-readable and
were embedding the appointment outcome in the event description, so the
redaction the templates enforced leaked straight out the calendar feed.
When a field is classified sensitive, audit feeds, exports, and any
future API alongside the UI.

## Why the session signing key is persisted beside the database

`HLIN_SECRET_KEY` is read from env (12-factor), but when it is unset the
app does not fall back to a per-process ephemeral key: it generates one
*once* and persists it as `.hlin-secret-key` next to the database, then
every worker reads that file. The container runs gunicorn with multiple
workers, each of which builds the app independently, so a per-process
key would sign session cookies differently per worker and a logged-in
editor would appear logged out on whichever worker did not mint their
cookie. Persisting (first writer wins via `O_EXCL`) makes the key stable
across workers and restarts with zero operator config, while still
honouring an explicit `HLIN_SECRET_KEY` when one is set. This is the
multi-worker-parity class the portfolio already tracks (the dev server
is single-process and never shows it).

## Why the audit log is atomic and captured by explicit calls

0.3.0 added an append-only `audit_log` (who changed what, when). Three design
choices are non-obvious and were settled by reading the sibling apps (mimir,
bragi) before building, both deliberately avoid ORM events for this.

**Explicit per-site capture, not a `before_flush` listener.** The tempting
design is one SQLAlchemy `before_flush` hook reading an ambient actor and
stamping every dirty row, zero call-site churn. Both mimir and bragi looked
at exactly that surface and chose an explicit `record()` call at each write
site instead. The win is richer, intent-bearing actions (`appointment.log_
outcome`, not a generic "update"), and the audit logic stays in the view
layer where the actor and the meaning of the change are known, rather than
hidden in a model event. The cost (one `audit.record(...)` line per mutating
route, 16 of them) is small and visible. So: when a new mutating route lands,
it must add its `audit.record` call, there is no automatic safety net.

**Atomic same-session write, not bragi's best-effort separate session.**
bragi opens its own `SessionLocal` for the audit row, commits it separately,
and swallows failures so an audit error can never break a publish, which
means a change can commit with its audit row silently missing. hlin instead
adds the audit row to the *request's* session, committed in the same
transaction as the change. The household chose a *full* history, so the
property that matters is no silent gaps, every committed change has its row
or neither commits. hlin is single-process, so bragi's reason for the
separate session (avoid a second connection deadlocking the writer under
multi-plugin load) does not apply. The tradeoff accepted: a (near-impossible)
audit-insert failure rolls back the user's action, correct for "the trail
must be complete".

**Weakly-referenced actor/target plus a username snapshot.** `audit_log` has
no foreign keys to `user` or the target rows. `actor_user_id`/`target_id` are
plain indexed integers, and `actor_username` is snapshotted at write time.
This means a row survives deletion of the login that made it (the name stays
readable) and outlives a deleted target (notably the row documenting that
very deletion), and a stale session user id can never FK-violate the atomic
write. bragi uses a `SET NULL` FK and loses the actor name on user deletion;
the snapshot is a small, deliberate improvement for trail durability.

## Why CI builds the image on every PR

Tier-C keeps the test suite off the artifact (tag) trigger, but the
Dockerfile is the one thing that genuinely cannot be checked on the dev
laptop (no docker/podman). So `ci.yml` builds the image (without pushing)
as a PR check: the first-ever build of the container ran on PR #1 and is
how we know the multi-stage uv build, the BuildKit cache mounts, and
`COPY --chmod` actually assemble. The tag-triggered `build-image.yml` then
only builds-and-pushes, no test re-run, consistent with Tier-C (a PR build
is not a test re-run).
