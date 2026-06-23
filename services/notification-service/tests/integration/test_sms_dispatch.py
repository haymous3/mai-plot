"""Integration tests for the SMS dispatch path (SCRUM-80).

Exercises NotificationDispatchService against the real DB with the inline SMS
dispatcher (no broker) + the in-memory Termii fake, asserting the rows written,
the sent_at stamp, and that SMS rows never leak into the SCRUM-82 in-app centre.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.termii import InMemoryTermiiClient
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.services.notification_dispatch import NotificationDispatchService
from app.services.sms_dispatch import InlineSmsDispatcher
from app.services.sms_send import SmsSendService

pytestmark = pytest.mark.asyncio


def _service(
    session: AsyncSession, termii: InMemoryTermiiClient
) -> tuple[NotificationDispatchService, NotificationRepository]:
    notifications = NotificationRepository(session)
    send = SmsSendService(notifications=notifications, users=UserRepository(session), termii=termii)
    service = NotificationDispatchService(
        notifications=notifications, sms=InlineSmsDispatcher(send_service=send)
    )
    return service, notifications


async def test_critical_alert_sends_sms_and_shows_in_app_once(
    clean_tables: None,
    async_session: AsyncSession,
    seed_user: Callable[..., UUID],
) -> None:
    user_id = seed_user(phone="08031234567")
    termii = InMemoryTermiiClient()
    service, notifications = _service(async_session, termii)

    result = await service.dispatch_critical_alert(
        user_id=user_id,
        type="offer_accepted",
        title="Offer accepted",
        body="Your offer was accepted.",
    )
    await async_session.commit()

    # SMS actually dialled, to the normalised E.164 number.
    assert len(termii.sent) == 1
    assert termii.sent[0].phone == "+2348031234567"
    assert termii.sent[0].message == "Your offer was accepted."

    # The sms row is stamped sent; the in_app row exists.
    sms_row = await notifications.get_by_id(result.sms_id)  # type: ignore[arg-type]
    assert sms_row is not None and sms_row.sent_at is not None

    # The in-app centre shows exactly ONE row (the in_app one) — the sms delivery
    # row does not double-surface in the feed.
    feed = await notifications.list_for_user(user_id, limit=10)
    assert [r.id for r in feed] == [result.in_app_id]
    assert feed[0].channel == "in_app"
    assert await notifications.unread_count(user_id) == 1


async def test_missing_phone_leaves_sms_unsent_but_keeps_in_app(
    clean_tables: None,
    async_session: AsyncSession,
    seed_user: Callable[..., UUID],
) -> None:
    user_id = seed_user()  # no user_pii row → no phone on file
    termii = InMemoryTermiiClient()
    service, notifications = _service(async_session, termii)

    result = await service.dispatch_critical_alert(
        user_id=user_id, type="loan_approved", body="Approved."
    )
    await async_session.commit()

    assert termii.sent == []  # nothing dialled
    sms_row = await notifications.get_by_id(result.sms_id)  # type: ignore[arg-type]
    assert sms_row is not None and sms_row.sent_at is None  # unsent
    # The in-app notification is unaffected by the SMS failure.
    feed = await notifications.list_for_user(user_id, limit=10)
    assert [r.id for r in feed] == [result.in_app_id]


async def test_termii_failure_is_swallowed_and_row_left_unsent(
    clean_tables: None,
    async_session: AsyncSession,
    seed_user: Callable[..., UUID],
) -> None:
    user_id = seed_user(phone="08031234567")
    termii = InMemoryTermiiClient(fail_next=True)
    service, notifications = _service(async_session, termii)

    # A Termii outage must not bubble out of dispatch (best-effort send).
    result = await service.dispatch_critical_alert(
        user_id=user_id, type="inspection_scheduled", body="Inspection booked."
    )
    await async_session.commit()

    assert termii.sent == []
    sms_row = await notifications.get_by_id(result.sms_id)  # type: ignore[arg-type]
    assert sms_row is not None and sms_row.sent_at is None
