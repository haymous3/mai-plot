"""Unit tests for NotificationDispatchService (SCRUM-80/79/81) — channel fan-out.

The repo + channel dispatchers are stubbed so we assert which rows get written
and whether each send is handed off, without a DB or any external client.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.notification_repo import NotificationRow
from app.repositories.preference_repo import NotificationPreferences
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


class _StubPreferences:
    def __init__(self, prefs: NotificationPreferences | None = None) -> None:
        self._prefs = prefs or NotificationPreferences()

    async def get(self, user_id: UUID) -> NotificationPreferences:
        return self._prefs


def _service(
    prefs: NotificationPreferences | None = None,
) -> tuple[
    NotificationDispatchService, _StubNotifRepo, _StubDispatcher, _StubDispatcher, _StubDispatcher
]:
    repo = _StubNotifRepo()
    sms = _StubDispatcher()
    push = _StubDispatcher()
    email = _StubDispatcher()
    service = NotificationDispatchService(
        notifications=repo,  # type: ignore[arg-type]
        preferences=_StubPreferences(prefs),  # type: ignore[arg-type]
        sms=sms,
        push=push,
        email=email,
    )
    return service, repo, sms, push, email


async def test_critical_alert_writes_core_channels_not_email() -> None:
    service, repo, sms, push, email = _service()

    result = await service.dispatch_critical_alert(
        user_id=uuid4(), type="offer_accepted", title="Offer accepted", body="Accepted."
    )

    channels = {c["channel"] for c in repo.created}
    assert channels == {"in_app", "sms", "push"}  # email is opt-in, not critical
    assert result.in_app_id is not None
    assert result.sms_id is not None
    assert result.push_id is not None
    assert result.email_id is None
    by_channel = {c["channel"]: c["sent_now"] for c in repo.created}
    assert by_channel == {"in_app": True, "sms": False, "push": False}
    assert sms.enqueued == [result.sms_id]
    assert push.enqueued == [result.push_id]
    assert email.enqueued == []


async def test_in_app_only_does_not_enqueue_any_send() -> None:
    service, repo, sms, push, email = _service()

    result = await service.dispatch(
        user_id=uuid4(), type="listing_approved", body="Live.", channels={"in_app"}
    )

    assert [c["channel"] for c in repo.created] == ["in_app"]
    assert result.sms_id is None
    assert result.push_id is None
    assert result.email_id is None
    assert sms.enqueued == []
    assert push.enqueued == []
    assert email.enqueued == []


async def test_email_channel_writes_row_and_enqueues_email() -> None:
    service, repo, sms, push, email = _service()

    result = await service.dispatch(
        user_id=uuid4(), type="document_verified", body="Verified.", channels={"email"}
    )

    assert [c["channel"] for c in repo.created] == ["email"]
    assert result.email_id is not None
    assert email.enqueued == [result.email_id]
    assert sms.enqueued == []
    assert push.enqueued == []


async def test_dispatch_suppresses_a_disabled_channel() -> None:
    # The user opted out of SMS — in_app + push still go, sms does not.
    service, repo, sms, push, _ = _service(NotificationPreferences(sms_enabled=False))

    result = await service.dispatch(
        user_id=uuid4(),
        type="offer_received",
        body="New offer.",
        channels={"in_app", "sms", "push"},
    )

    channels = {c["channel"] for c in repo.created}
    assert channels == {"in_app", "push"}  # sms suppressed by preference
    assert result.sms_id is None
    assert sms.enqueued == []
    assert push.enqueued == [result.push_id]


async def test_critical_alert_bypasses_preferences() -> None:
    # Even with everything opted out, a critical alert still goes (force).
    all_off = NotificationPreferences(push_enabled=False, sms_enabled=False, email_enabled=False)
    service, repo, sms, push, _ = _service(all_off)

    result = await service.dispatch_critical_alert(
        user_id=uuid4(), type="offer_accepted", body="Accepted."
    )

    assert {c["channel"] for c in repo.created} == {"in_app", "sms", "push"}
    assert sms.enqueued == [result.sms_id]
    assert push.enqueued == [result.push_id]
