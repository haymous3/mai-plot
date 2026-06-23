"""Unit tests for PushSendService (SCRUM-79) — fan-out, pruning, retry.

Repos are stubbed; the Web Push client is the real in-memory fake so we can
assert exactly what was pushed and which subscriptions got pruned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.web_push import InMemoryWebPushClient, WebPushError
from app.repositories.notification_repo import NotificationRow
from app.repositories.push_subscription_repo import PushSubscriptionRow
from app.services.push_send import PushOutcome, PushSendService

pytestmark = pytest.mark.asyncio


def _notif(*, channel: str = "push", sent_at: datetime | None = None) -> NotificationRow:
    return NotificationRow(
        id=uuid4(),
        user_id=uuid4(),
        channel=channel,
        type="offer_accepted",
        title="Offer accepted",
        body="Your offer was accepted.",
        reference_type="transaction",
        reference_id=uuid4(),
        is_read=False,
        sent_at=sent_at,
        read_at=None,
        created_at=datetime.now(UTC),
    )


def _sub(endpoint: str) -> PushSubscriptionRow:
    now = datetime.now(UTC)
    return PushSubscriptionRow(
        id=uuid4(),
        user_id=uuid4(),
        endpoint=endpoint,
        p256dh="key",
        auth="auth",
        user_agent=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
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


class _StubSubRepo:
    def __init__(self, subs: list[PushSubscriptionRow]) -> None:
        self._subs = subs
        self.deleted: list[UUID] = []

    async def list_active_for_user(self, user_id: UUID) -> list[PushSubscriptionRow]:
        return self._subs

    async def soft_delete(self, subscription_id: UUID) -> bool:
        self.deleted.append(subscription_id)
        return True


def _service(
    *,
    row: NotificationRow | None,
    subs: list[PushSubscriptionRow],
    web_push: InMemoryWebPushClient,
) -> tuple[PushSendService, _StubNotifRepo, _StubSubRepo]:
    notif_repo = _StubNotifRepo(row)
    sub_repo = _StubSubRepo(subs)
    service = PushSendService(notifications=notif_repo, subscriptions=sub_repo, web_push=web_push)  # type: ignore[arg-type]
    return service, notif_repo, sub_repo


async def test_delivers_to_all_devices_and_marks_sent() -> None:
    row = _notif()
    web_push = InMemoryWebPushClient()
    service, notif_repo, _ = _service(
        row=row, subs=[_sub("https://push/a"), _sub("https://push/b")], web_push=web_push
    )

    outcome = await service.send(row.id)

    assert outcome is PushOutcome.SENT
    assert {p.endpoint for p in web_push.sent} == {"https://push/a", "https://push/b"}
    assert notif_repo.marked == [row.id]


async def test_already_sent_is_noop() -> None:
    row = _notif(sent_at=datetime.now(UTC))
    web_push = InMemoryWebPushClient()
    service, _, _ = _service(row=row, subs=[_sub("https://push/a")], web_push=web_push)

    assert await service.send(row.id) is PushOutcome.ALREADY_SENT
    assert web_push.sent == []


async def test_missing_row_is_not_found() -> None:
    web_push = InMemoryWebPushClient()
    service, _, _ = _service(row=None, subs=[], web_push=web_push)
    assert await service.send(uuid4()) is PushOutcome.NOT_FOUND


async def test_non_push_row_is_skipped() -> None:
    row = _notif(channel="sms")
    web_push = InMemoryWebPushClient()
    service, _, _ = _service(row=row, subs=[_sub("https://push/a")], web_push=web_push)
    assert await service.send(row.id) is PushOutcome.NOT_PUSH
    assert web_push.sent == []


async def test_no_subscriptions_is_terminal() -> None:
    row = _notif()
    web_push = InMemoryWebPushClient()
    service, notif_repo, _ = _service(row=row, subs=[], web_push=web_push)

    assert await service.send(row.id) is PushOutcome.NO_SUBSCRIPTIONS
    assert notif_repo.marked == []  # nothing delivered → not stamped


async def test_expired_subscription_is_pruned() -> None:
    row = _notif()
    sub = _sub("https://push/dead")
    web_push = InMemoryWebPushClient(gone_next=True)
    service, notif_repo, sub_repo = _service(row=row, subs=[sub], web_push=web_push)

    outcome = await service.send(row.id)

    assert outcome is PushOutcome.ALL_EXPIRED
    assert sub_repo.deleted == [sub.id]
    assert notif_repo.marked == []


async def test_one_dead_one_live_delivers_and_prunes() -> None:
    row = _notif()
    dead = _sub("https://push/dead")
    live = _sub("https://push/live")
    web_push = InMemoryWebPushClient(gone_next=True)  # first call (dead) is gone
    service, notif_repo, sub_repo = _service(row=row, subs=[dead, live], web_push=web_push)

    outcome = await service.send(row.id)

    assert outcome is PushOutcome.SENT
    assert [p.endpoint for p in web_push.sent] == ["https://push/live"]
    assert sub_repo.deleted == [dead.id]
    assert notif_repo.marked == [row.id]


async def test_all_transient_failures_raise_for_retry() -> None:
    row = _notif()
    web_push = InMemoryWebPushClient(fail_next=True)  # single sub, transient fail
    service, notif_repo, _ = _service(row=row, subs=[_sub("https://push/a")], web_push=web_push)

    with pytest.raises(WebPushError):
        await service.send(row.id)
    assert notif_repo.marked == []
