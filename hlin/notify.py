"""Optional outbound reminders via ntfy.

The single notification channel the spec allows (non-goal: more than one).
``build_reminder`` turns the recall panel into a short message;
``send_ntfy`` POSTs it to the configured ntfy topic using stdlib urllib
(no ``requests`` dependency). There is no in-app scheduler: the operator
runs ``flask --app hlin remind`` from cron / a systemd timer.

Privacy note: the message contains household names and appointment kinds,
so point ntfy at a self-hosted server or an unguessable, access-controlled
topic, not a public ntfy.sh topic.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Sequence

from .recall import RecallItem, RecallStatus
from .settings import Settings


def build_reminder(items: Sequence[RecallItem]) -> str | None:
    """One line per attention item, or None when nothing is due."""
    if not items:
        return None
    lines = []
    for item in items:
        flag = "OVERDUE" if item.status is RecallStatus.OVERDUE else "due"
        person = item.obligation.person.name
        lines.append(f"- {person} {item.obligation.kind} {flag} {item.next_due}")
    return "\n".join(lines)


def send_ntfy(settings: Settings, message: str, *, title: str = "hlin reminders") -> None:
    """POST ``message`` to the configured ntfy topic. Raises if ntfy is not
    configured; urllib raises on any non-2xx response."""
    if not settings.ntfy_url or not settings.ntfy_topic:
        raise RuntimeError("ntfy is not configured (set HLIN_NTFY_URL and HLIN_NTFY_TOPIC)")
    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    request = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={"Title": title},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=10)  # noqa: S310 (operator-configured URL)
