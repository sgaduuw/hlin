"""Recall logic tests.

The recall functions are pure over detached model instances, so these
construct ``RecurringObligation`` / ``Appointment`` objects directly (no
session) and pin a fixed ``today`` for determinism.
"""

from __future__ import annotations

from datetime import date, timedelta

from hlin.models import Appointment, AppointmentStatus, RecurringObligation
from hlin.recall import (
    RecallStatus,
    add_months,
    classify,
    compute_recall,
    is_covered,
    next_due_date,
    obligations_needing_attention,
)

TODAY = date(2026, 6, 28)
HORIZON = 60


def make_obligation(**kw) -> RecurringObligation:
    kw.setdefault("active", True)
    kw.setdefault("kind", "tandarts")
    kw.setdefault("interval_months", 6)
    kw.setdefault("person_id", 1)
    return RecurringObligation(**kw)


def booked(person_id: int = 1, kind: str = "tandarts") -> Appointment:
    return Appointment(person_id=person_id, kind=kind, status=AppointmentStatus.BOOKED)


# --- add_months ---------------------------------------------------------


def test_add_months_basic():
    assert add_months(date(2026, 1, 15), 6) == date(2026, 7, 15)


def test_add_months_year_rollover():
    assert add_months(date(2026, 9, 1), 6) == date(2027, 3, 1)


def test_add_months_clamps_short_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_add_months_clamps_to_leap_day():
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)


# --- next_due_date ------------------------------------------------------


def test_next_due_from_last_done():
    obligation = make_obligation(last_done=date(2026, 1, 1), interval_months=6)
    assert next_due_date(obligation, today=TODAY) == date(2026, 7, 1)


def test_next_due_never_done_is_today():
    assert next_due_date(make_obligation(last_done=None), today=TODAY) == TODAY


# --- classify (timing only) ---------------------------------------------


def test_classify_overdue():
    assert (
        classify(TODAY - timedelta(days=1), today=TODAY, horizon_days=HORIZON)
        is RecallStatus.OVERDUE
    )


def test_classify_today_is_due_soon():
    assert classify(TODAY, today=TODAY, horizon_days=HORIZON) is RecallStatus.DUE_SOON


def test_classify_horizon_edge_is_due_soon():
    edge = TODAY + timedelta(days=HORIZON)
    assert classify(edge, today=TODAY, horizon_days=HORIZON) is RecallStatus.DUE_SOON


def test_classify_just_past_horizon_is_future():
    beyond = TODAY + timedelta(days=HORIZON + 1)
    assert classify(beyond, today=TODAY, horizon_days=HORIZON) is RecallStatus.FUTURE


# --- is_covered ---------------------------------------------------------


def test_is_covered_matches_person_and_kind():
    obligation = make_obligation(person_id=1, kind="tandarts")
    assert is_covered(obligation, [booked(1, "tandarts")])


def test_is_covered_rejects_wrong_kind_person_or_status():
    obligation = make_obligation(person_id=1, kind="tandarts")
    assert not is_covered(obligation, [booked(1, "huisarts")])
    assert not is_covered(obligation, [booked(2, "tandarts")])
    due = Appointment(person_id=1, kind="tandarts", status=AppointmentStatus.DUE)
    assert not is_covered(obligation, [due])


# --- compute_recall -----------------------------------------------------


def test_compute_recall_skips_inactive():
    obligation = make_obligation(last_done=date(2025, 1, 1), active=False)
    assert compute_recall([obligation], today=TODAY, horizon_days=HORIZON) == []


# --- obligations_needing_attention (the panel) --------------------------


def test_panel_overdue_before_due_soon():
    overdue = make_obligation(person_id=1, last_done=date(2025, 1, 1))  # due 2025-07-01
    due_soon = make_obligation(person_id=2, last_done=date(2026, 1, 1))  # due 2026-07-01
    future = make_obligation(person_id=3, last_done=date(2026, 6, 1), interval_months=12)
    panel = obligations_needing_attention(
        [due_soon, future, overdue], today=TODAY, horizon_days=HORIZON
    )
    assert [it.obligation for it in panel] == [overdue, due_soon]
    assert panel[0].status is RecallStatus.OVERDUE
    assert panel[1].status is RecallStatus.DUE_SOON


def test_panel_overdue_sorted_earliest_first():
    less = make_obligation(person_id=1, last_done=date(2025, 1, 1))  # due 2025-07-01
    more = make_obligation(person_id=2, last_done=date(2024, 1, 1))  # due 2024-07-01
    panel = obligations_needing_attention([less, more], today=TODAY, horizon_days=HORIZON)
    assert [it.obligation for it in panel] == [more, less]


def test_panel_excludes_covered_even_when_overdue():
    overdue = make_obligation(person_id=1, kind="tandarts", last_done=date(2025, 1, 1))
    panel = obligations_needing_attention(
        [overdue], [booked(1, "tandarts")], today=TODAY, horizon_days=HORIZON
    )
    assert panel == []


def test_panel_excludes_future():
    future = make_obligation(last_done=date(2026, 6, 1), interval_months=12)  # due 2027-06-01
    assert obligations_needing_attention([future], today=TODAY, horizon_days=HORIZON) == []
