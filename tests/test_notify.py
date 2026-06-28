"""Reminder-building and ntfy-send tests.

``send_ntfy`` is tested with urlopen monkeypatched so no network is hit.
"""

from __future__ import annotations

from datetime import date

import pytest

from hlin import notify
from hlin.models import Person, RecurringObligation, Role
from hlin.recall import RecallItem, RecallStatus
from hlin.settings import Settings


def _item(status: RecallStatus, next_due: date, *, name="Alice", kind="tandarts") -> RecallItem:
    obligation = RecurringObligation(person_id=1, kind=kind, interval_months=6)
    obligation.person = Person(name=name, role=Role.CHILD)
    return RecallItem(obligation=obligation, next_due=next_due, status=status, covered=False)


def test_build_reminder_empty_is_none():
    assert notify.build_reminder([]) is None


def test_build_reminder_marks_overdue_and_due():
    message = notify.build_reminder(
        [
            _item(RecallStatus.OVERDUE, date(2026, 1, 1)),
            _item(RecallStatus.DUE_SOON, date(2026, 8, 1), name="Erin", kind="huisarts"),
        ]
    )
    assert "Alice tandarts OVERDUE 2026-01-01" in message
    assert "Erin huisarts due 2026-08-01" in message


def test_send_ntfy_requires_configuration():
    with pytest.raises(RuntimeError):
        notify.send_ntfy(Settings(ntfy_url=None, ntfy_topic=None), "hi")


def test_send_ntfy_posts_to_topic(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["title"] = request.get_header("Title")
        captured["method"] = request.get_method()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    notify.send_ntfy(Settings(ntfy_url="https://ntfy.example/", ntfy_topic="hlin-abc"), "two due")

    assert captured["url"] == "https://ntfy.example/hlin-abc"
    assert captured["data"] == b"two due"
    assert captured["title"] == "hlin reminders"
    assert captured["method"] == "POST"
