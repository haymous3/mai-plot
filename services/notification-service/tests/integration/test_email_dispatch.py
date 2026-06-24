"""Integration tests for the email dispatch path (SCRUM-81).

Exercises NotificationDispatchService against the real DB with the inline email
dispatcher + the in-memory SES fake, asserting the row written, the sent_at
stamp, and that email rows never leak into the SCRUM-82 in-app centre.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ses_email import InMemorySesClient
from app.adapters.termii import InMemoryTermiiClient
from app.adapters.web_push import InMemoryWebPushClient
from app.repositories.notification_repo import NotificationRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.repositories.user_repo import UserRepository
from app.services.email_dispatch import InlineEmailDispatcher
from app.services.email_send import EmailSendService
from app.services.notification_dispatch import NotificationDispatchService
from app.services.push_dispatch import InlinePushDispatcher
from app.services.push_send import PushSendService
from app.services.sms_dispatch import InlineSmsDispatcher
from app.services.sms_send import SmsSendService

pytestmark = pytest.mark.asyncio


def _service(
    session: AsyncSession, ses: InMemorySesClient
) -> tuple[NotificationDispatchService, NotificationRepository]:
    notifications = NotificationRepository(session)
    users = UserRepository(session)
    sms_send = SmsSendService(
        notifications=notifications, users=users, termii=InMemoryTermiiClient()
    )
    push_send = PushSendService(
        notifications=notifications,
        subscriptions=PushSubscriptionRepository(session),
        web_push=InMemoryWebPushClient(),
    )
    email_send = EmailSendService(
        notifications=notifications,
        users=users,
        email_client=ses,
        unsubscribe_base_url="https://maiplot.ng/notifications/unsubscribe",
    )
    service = NotificationDispatchService(
        notifications=notifications,
        sms=InlineSmsDispatcher(send_service=sms_send),
        push=InlinePushDispatcher(send_service=push_send),
        email=InlineEmailDispatcher(send_service=email_send),
    )
    return service, notifications


async def test_dispatch_emails_user_and_excludes_from_centre(
    clean_tables: None,
    async_session: AsyncSession,
    seed_user: Callable[..., UUID],
) -> None:
    user_id = seed_user(email="buyer@example.com")
    ses = InMemorySesClient()
    service, notifications = _service(async_session, ses)

    result = await service.dispatch(
        user_id=user_id,
        type="document_verified",
        title="Document verified",
        body="Your title document was verified.",
        channels={"email"},
    )
    await async_session.commit()

    assert len(ses.sent) == 1
    assert ses.sent[0].to == "buyer@example.com"
    assert ses.sent[0].subject == "Document verified"

    email_row = await notifications.get_by_id(result.email_id)  # type: ignore[arg-type]
    assert email_row is not None and email_row.sent_at is not None

    # The in-app centre never shows the email delivery row.
    feed = await notifications.list_for_user(user_id, limit=10)
    assert feed == []
    assert await notifications.unread_count(user_id) == 0


async def test_dispatch_without_email_on_file_leaves_row_unsent(
    clean_tables: None,
    async_session: AsyncSession,
    seed_user: Callable[..., UUID],
) -> None:
    user_id = seed_user()  # no email
    ses = InMemorySesClient()
    service, notifications = _service(async_session, ses)

    result = await service.dispatch(
        user_id=user_id, type="document_verified", body="Verified.", channels={"email"}
    )
    await async_session.commit()

    assert ses.sent == []
    email_row = await notifications.get_by_id(result.email_id)  # type: ignore[arg-type]
    assert email_row is not None and email_row.sent_at is None
