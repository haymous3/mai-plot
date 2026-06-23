"""Unit tests for NotificationDispatchService (SCRUM-80/79) — channel fan-out.

The repo + SMS/push dispatchers are stubbed so we assert which rows get written
and whether each send is handed off, without a DB, Termii, or a push service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.notification_repo import NotificationRow
from app.services.notification_dispatch import NotificationDispatchService

pytestmark = pytest.mark.asyncio


class _StubNotifRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []

    async def create(
        self,
        *,
        user_id: UUID,
        channel: str,
        type: str,
        body: str,
        title: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        sent_now: bool = False,
    ) -> NotificationRow:
        self.created.append({"channel": channel, "type": type, "sent_now": sent_now})
        return NotificationRow(
            id=uuid4(),
            user_id=user_id,
            channel=channel,
            type=type,
            title=title,
            body=body,
            reference_type=reference_type,
            reference_id=reference_id,
            is_read=False,
            sent_at=datetime.now(UTC) if sent_now else None,
            read_at=None,
            created_at=datetime.now(UTC),
        )


class _StubDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []

    async def enqueue(self, notification_id: UUID) -> None:
        self.enqueued.append(notification_id)


def _service() -> tuple[
    NotificationDispatchService, _StubNotifRepo, _StubDispatcher, _StubDispatcher
]:
    repo = _StubNotifRepo()
    sms = _StubDispatcher()
    push = _StubDispatcher()
    service = NotificationDispatchService(notifications=repo, sms=sms, push=push)  # type: ignore[arg-type]
    return service, repo, sms, push


async def test_critical_alert_writes_all_channels_and_enqueues_sends() -> None:
    service, repo, sms, push = _service()

    result = await service.dispatch_critical_alert(
        user_id=uuid4(), type="offer_accepted", title="Offer accepted", body="Accepted."
    )

    channels = {c["channel"] for c in repo.created}
    assert channels == {"in_app", "sms", "push"}
    assert result.in_app_id is not None
    assert result.sms_id is not None
    assert result.push_id is not None
    # in_app is delivered on write; sms + push wait for their send to confirm.
    by_channel = {c["channel"]: c["sent_now"] for c in repo.created}
    assert by_channel == {"in_app": True, "sms": False, "push": False}
    assert sms.enqueued == [result.sms_id]
    assert push.enqueued == [result.push_id]


async def test_in_app_only_does_not_enqueue_any_send() -> None:
    service, repo, sms, push = _service()

    result = await service.dispatch(
        user_id=uuid4(), type="listing_approved", body="Live.", channels={"in_app"}
    )

    assert [c["channel"] for c in repo.created] == ["in_app"]
    assert result.sms_id is None
    assert result.push_id is None
    assert sms.enqueued == []
    assert push.enqueued == []


async def test_push_only_enqueues_push_without_in_app_or_sms() -> None:
    service, repo, sms, push = _service()

    result = await service.dispatch(
        user_id=uuid4(), type="inspection_scheduled", body="Booked.", channels={"push"}
    )

    assert [c["channel"] for c in repo.created] == ["push"]
    assert result.in_app_id is None
    assert result.sms_id is None
    assert result.push_id is not None
    assert sms.enqueued == []
    assert push.enqueued == [result.push_id]
