"""Unit tests for SmsSendService (SCRUM-80) — outcomes + retry signalling.

Repos are stubbed; the Termii client is the real in-memory fake so we can assert
exactly what was dialled without a network or DB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.termii import InMemoryTermiiClient, TermiiError
from app.repositories.notification_repo import NotificationRow
from app.services.sms_send import SmsOutcome, SmsSendService

pytestmark = pytest.mark.asyncio


def _row(*, channel: str = "sms", sent_at: datetime | None = None) -> NotificationRow:
    return NotificationRow(
        id=uuid4(),
        user_id=uuid4(),
        channel=channel,
        type="offer_accepted",
        title="Offer accepted",
        body="Your offer was accepted.",
        reference_type=None,
        reference_id=None,
        is_read=False,
        sent_at=sent_at,
        read_at=None,
        created_at=datetime.now(UTC),
    )


class _StubNotifRepo:
    def __init__(self, row: NotificationRow | None) -> None:
        self._row = row
        self.marked: list[UUID] = []

    async def get_by_id(self, notification_id: UUID) -> NotificationRow | None:
        return self._row

    async def mark_sent(self, notification_id: UUID) -> bool:
        self.marked.append(notification_id)
        return True


class _StubUserRepo:
    def __init__(self, phone: str | None) -> None:
        self._phone = phone

    async def get_phone(self, user_id: UUID) -> str | None:
        return self._phone


def _service(
    *, row: NotificationRow | None, phone: str | None, termii: InMemoryTermiiClient
) -> tuple[SmsSendService, _StubNotifRepo]:
    repo = _StubNotifRepo(row)
    service = SmsSendService(notifications=repo, users=_StubUserRepo(phone), termii=termii)  # type: ignore[arg-type]
    return service, repo


async def test_sends_and_marks_sent() -> None:
    row = _row()
    termii = InMemoryTermiiClient()
    service, repo = _service(row=row, phone="08031234567", termii=termii)

    outcome = await service.send(row.id)

    assert outcome is SmsOutcome.SENT
    assert len(termii.sent) == 1
    assert termii.sent[0].phone == "+2348031234567"
    assert termii.sent[0].message == row.body
    assert repo.marked == [row.id]


async def test_already_sent_is_noop() -> None:
    row = _row(sent_at=datetime.now(UTC))
    termii = InMemoryTermiiClient()
    service, repo = _service(row=row, phone="08031234567", termii=termii)

    outcome = await service.send(row.id)

    assert outcome is SmsOutcome.ALREADY_SENT
    assert termii.sent == []
    assert repo.marked == []


async def test_missing_row_is_not_found() -> None:
    termii = InMemoryTermiiClient()
    service, _ = _service(row=None, phone="08031234567", termii=termii)

    assert await service.send(uuid4()) is SmsOutcome.NOT_FOUND
    assert termii.sent == []


async def test_non_sms_row_is_skipped() -> None:
    row = _row(channel="in_app")
    termii = InMemoryTermiiClient()
    service, _ = _service(row=row, phone="08031234567", termii=termii)

    assert await service.send(row.id) is SmsOutcome.NOT_SMS
    assert termii.sent == []


async def test_invalid_number_is_terminal() -> None:
    row = _row()
    termii = InMemoryTermiiClient()
    service, repo = _service(row=row, phone=None, termii=termii)

    outcome = await service.send(row.id)

    assert outcome is SmsOutcome.INVALID_NUMBER
    assert termii.sent == []
    assert repo.marked == []  # not sent, so not stamped


async def test_termii_failure_raises_for_retry() -> None:
    row = _row()
    termii = InMemoryTermiiClient(fail_next=True)
    service, repo = _service(row=row, phone="08031234567", termii=termii)

    with pytest.raises(TermiiError):
        await service.send(row.id)
    assert repo.marked == []  # not stamped on failure → a retry can re-send
