"""The inspection-assignment alert (SCRUM-72, extended by SCRUM-213).

An assignment is a 2-hour offer. Before SCRUM-213 it went out on in_app + push +
sms only: an in-app badge the realtor sees when they next log in, a browser push
they most likely never granted, and an SMS that cannot reach a Nigerian network
from the current sender at all (CLAUDE.md §2 / SCRUM-177). Email is the one
channel that arrives, so its presence is pinned here rather than left to a code
review — and so is what the message says, because a mail that only says "you
have an assignment" makes the realtor log in to find out whether the job is even
reachable for them before the window closes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.services.inspection_notifier import (
    CeleryInspectionNotifier,
    build_assignment_body,
    format_inspection_datetime,
)

_BROKER = "memory://"


class _RecordingApp:
    """Records the publish without a broker — the producer builds its Celery app
    at construction but does not connect until a send."""

    def __init__(self) -> None:
        self.kwargs: list[dict[str, object]] = []

    def send_task(self, name: str, **kwargs: object) -> None:
        payload = kwargs.get("kwargs")
        self.kwargs.append(payload if isinstance(payload, dict) else {})


@pytest.mark.asyncio
async def test_assignment_is_emailed() -> None:
    notifier = CeleryInspectionNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.assigned(realtor_id=uuid4(), inspection_id=uuid4())

    assert "email" in recorder.kwargs[0]["channels"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_assignment_body_names_the_property_and_time() -> None:
    """The mail has to stand on its own: where, and when."""
    notifier = CeleryInspectionNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.assigned(
        realtor_id=uuid4(),
        inspection_id=uuid4(),
        property_title="4-bed duplex, Lekki",
        proposed_date=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
    )

    body = recorder.kwargs[0]["body"]
    assert isinstance(body, str)
    assert "4-bed duplex, Lekki" in body
    assert "15 Sep 2026" in body


def test_dates_are_rendered_in_lagos_time() -> None:
    """Rows are UTC; a realtor reads local time. 09:00 UTC is 10:00 in Lagos, and
    getting this wrong sends them to a property an hour before the buyer."""
    rendered = format_inspection_datetime(datetime(2026, 9, 15, 9, 0, tzinfo=UTC))

    assert rendered == "Tue 15 Sep 2026, 10:00 AM WAT"


def test_a_non_utc_input_is_converted_not_relabelled() -> None:
    """Same instant, written in another zone: the output must not change."""
    berlin = datetime(2026, 9, 15, 11, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    assert format_inspection_datetime(berlin) == "Tue 15 Sep 2026, 10:00 AM WAT"


def test_body_degrades_when_the_caller_has_no_context() -> None:
    """The sweep's row is built for proximity, not prose. A vague alert beats a
    late one, so a missing title or date drops that clause and nothing else."""
    bare = build_assignment_body()

    assert "Accept it within 2 hours" in bare
    assert "None" not in bare


def test_body_uses_whichever_half_is_available() -> None:
    date_only = build_assignment_body(proposed_date=datetime(2026, 9, 15, 9, 0, tzinfo=UTC))
    title_only = build_assignment_body(property_title="4-bed duplex, Lekki")

    assert "15 Sep 2026" in date_only
    assert "4-bed duplex, Lekki" in title_only
    assert "None" not in date_only and "None" not in title_only
