"""Recall logic: derive next-due dates from recurring obligations and
classify them for the dashboard "Coming up / Overdue" panel.

Pure functions over the model (no DB access, no implicit clock), so they
are cheap to test and the UI and feed layers can call them with whatever
``today`` they choose. The derived next-due date is never stored
(``last_done + interval_months``) so it cannot drift out of sync.
"""

from __future__ import annotations

import calendar
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from .models import Appointment, AppointmentStatus, RecurringObligation


class RecallStatus(enum.StrEnum):
    OVERDUE = "overdue"  # next_due is in the past
    DUE_SOON = "due_soon"  # next_due within the horizon (includes today)
    FUTURE = "future"  # next_due beyond the horizon


@dataclass(frozen=True)
class RecallItem:
    obligation: RecurringObligation
    next_due: date
    status: RecallStatus
    covered: bool  # a matching booked appointment already exists


def add_months(d: date, months: int) -> date:
    """Add whole months, clamping the day to the target month's length.

    e.g. 31 Jan + 1 month -> 28/29 Feb. stdlib only, no dateutil dependency.
    """
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_due_date(obligation: RecurringObligation, *, today: date) -> date:
    """Derived next-due date. A never-done obligation (``last_done is None``)
    is treated as due as of today."""
    if obligation.last_done is None:
        return today
    return add_months(obligation.last_done, obligation.interval_months)


def classify(next_due: date, *, today: date, horizon_days: int) -> RecallStatus:
    """Timing classification only; coverage is tracked separately."""
    if next_due < today:
        return RecallStatus.OVERDUE
    if next_due <= today + timedelta(days=horizon_days):
        return RecallStatus.DUE_SOON
    return RecallStatus.FUTURE


def is_covered(obligation: RecurringObligation, appointments: Iterable[Appointment]) -> bool:
    """True if a booked appointment already exists for this obligation's
    person and kind, so a past-due obligation is handled rather than overdue.
    """
    return any(
        appt.status == AppointmentStatus.BOOKED
        and appt.person_id == obligation.person_id
        and appt.kind == obligation.kind
        for appt in appointments
    )


def compute_recall(
    obligations: Iterable[RecurringObligation],
    appointments: Iterable[Appointment] = (),
    *,
    today: date,
    horizon_days: int,
) -> list[RecallItem]:
    """One ``RecallItem`` per active obligation, timing classified and
    coverage flagged. Order is not significant; see
    :func:`obligations_needing_attention` for the dashboard ordering."""
    appts = list(appointments)
    items: list[RecallItem] = []
    for obligation in obligations:
        if not obligation.active:
            continue
        due = next_due_date(obligation, today=today)
        items.append(
            RecallItem(
                obligation=obligation,
                next_due=due,
                status=classify(due, today=today, horizon_days=horizon_days),
                covered=is_covered(obligation, appts),
            )
        )
    return items


# Overdue sorts before due-soon; future never reaches the panel.
_STATUS_RANK = {RecallStatus.OVERDUE: 0, RecallStatus.DUE_SOON: 1, RecallStatus.FUTURE: 2}


def obligations_needing_attention(
    obligations: Iterable[RecurringObligation],
    appointments: Iterable[Appointment] = (),
    *,
    today: date,
    horizon_days: int,
) -> list[RecallItem]:
    """The dashboard panel: uncovered obligations that are overdue or due
    within the horizon, overdue first, then earliest next-due first."""
    items = compute_recall(obligations, appointments, today=today, horizon_days=horizon_days)
    panel = [it for it in items if not it.covered and it.status is not RecallStatus.FUTURE]
    panel.sort(key=lambda it: (_STATUS_RANK[it.status], it.next_due))
    return panel
