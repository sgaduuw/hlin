"""Read-only ``.ics`` feed routes.

Stable URLs for the household's CalDAV clients:

* ``/feeds/all.ics``            -- every person's appointments + due-dates
* ``/feeds/social.ics``        -- contact birthdays
* ``/feeds/person/<id>.ics``   -- one person's appointments + due-dates

Person feeds are keyed on the numeric id (stable across renames) rather
than a name slug. The calendar is built and serialised inside the session
block so the feed builders can follow relationships lazily.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, Response, abort

from .. import feeds as feedgen
from .. import store
from ..db import SessionLocal

bp = Blueprint("feeds", __name__, url_prefix="/feeds")


def _ics(cal) -> Response:
    return Response(feedgen.to_ics(cal), mimetype="text/calendar")


@bp.get("/all.ics")
def all_feed() -> Response:
    today = date.today()
    with SessionLocal() as session:
        return _ics(feedgen.combined_calendar(store.list_persons(session), today=today))


@bp.get("/social.ics")
def social_feed() -> Response:
    with SessionLocal() as session:
        return _ics(feedgen.social_calendar(store.list_contacts(session)))


@bp.get("/person/<int:person_id>.ics")
def person_feed(person_id: int) -> Response:
    today = date.today()
    with SessionLocal() as session:
        person = store.get_person(session, person_id)
        if person is None:
            abort(404)
        return _ics(feedgen.person_calendar(person, today=today))
