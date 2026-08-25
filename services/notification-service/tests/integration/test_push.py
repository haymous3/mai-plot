"""Integration tests for Web Push (SCRUM-79).

Two surfaces: the subscription register/unregister HTTP endpoints, and the push
dispatch path (dispatch -> push row -> inline Web Push send against the
in-memory fake, with dead-subscription pruning).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.web_push import InMemoryWebPushClient
from app.repositories.notification_repo import NotificationRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.services.notification_dispatch import NotificationDispatchService
from app.services.push_dispatch import InlinePushDispatcher
from app.services.push_send import PushSendService
from app.services.sms_dispatch import InlineSmsDispatcher
from app.services.sms_send import SmsSendService

pytestmark = pytest.mark.asyncio

_SUB_BODY = {
    "endpoint": "https://fcm.googleapis.com/wp/abc123",
    "keys": {"p256dh": "BPkeymaterial", "auth": "authsecret"},
}


def _active_sub_count(db_engine: Engine, user_id: UUID) -> int:
    with db_engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM push_subscriptions "
                "WHERE user_id = :uid AND deleted_at IS NULL"
            ),
            {"uid": user_id},
        ).scalar_one()
    assert isinstance(count, int)
    return count


# --- register / unregister endpoints -------------------------------------------------


async def test_register_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.post("/notifications/push/subscriptions", json=_SUB_BODY)
    assert resp.status_code == 401


async def test_register_stores_subscription(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user()
    resp = await http_client.post(
        "/notifications/push/subscriptions",
        json=_SUB_BODY,
        headers=auth_header(mint_token(user_id, "buyer")),
    )
    assert resp.status_code == 201
    assert "id" in resp.json()
    assert _active_sub_count(db_engine, user_id) == 1


async def test_register_is_idempotent_on_endpoint(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user()
    headers = auth_header(mint_token(user_id, "buyer"))
    first = await http_client.post(
        "/notifications/push/subscriptions", json=_SUB_BODY, headers=headers
    )
    second = await http_client.post(
        "/notifications/push/subscriptions", json=_SUB_BODY, headers=headers
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]  # same (user, endpoint) upserts
    assert _active_sub_count(db_engine, user_id) == 1


async def test_unregister_removes_then_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user()
    headers = auth_header(mint_token(user_id, "buyer"))
    await http_client.post("/notifications/push/subscriptions", json=_SUB_BODY, headers=headers)

    # httpx requires request() to send a body on DELETE.
    gone = await http_client.request(
        "DELETE",
        "/notifications/push/subscriptions",
        json={"endpoint": _SUB_BODY["endpoint"]},
        headers=headers,
    )
    assert gone.status_code == 204

    again = await http_client.request(
        "DELETE",
        "/notifications/push/subscriptions",
        json={"endpoint": _SUB_BODY["endpoint"]},
        headers=headers,
    )
    assert again.status_code == 404
    assert again.json()["error_code"] == "PUSH_SUBSCRIPTION_NOT_FOUND"


# --- dispatch -> push send -----------------------------------------------------------


def _dispatch_service(
    session: AsyncSession, web_push: InMemoryWebPushClient
) -> tuple[NotificationDispatchService, NotificationRepository, PushSubscriptionRepository]:
    notifications = NotificationRepository(session)
    subscriptions = PushSubscriptionRepository(session)
    # SMS + email aren't exercised here; unused inline dispatchers with fakes are fine.
    from app.adapters.ses_email import InMemorySesClient
    from app.adapters.termii import InMemoryTermiiClient
    from app.repositories.preference_repo import PreferenceRepository
    from app.repositories.user_repo import UserRepository
    from app.services.email_dispatch import InlineEmailDispatcher
    from app.services.email_send import EmailSendService

    users = UserRepository(session)
    sms_send = SmsSendService(
        notifications=notifications, users=users, termii=InMemoryTermiiClient()
    )
    push_send = PushSendService(
        notifications=notifications, subscriptions=subscriptions, web_push=web_push
    )
    email_send = EmailSendService(
        notifications=notifications,
        users=users,
        email_client=InMemorySesClient(),
        unsubscribe_base_url="https://maihomme.com/notifications/unsubscribe",
        unsubscribe_secret="test-secret",
    )
    service = NotificationDispatchService(
        notifications=notifications,
        preferences=PreferenceRepository(session),
        sms=InlineSmsDispatcher(send_service=sms_send),
        push=InlinePushDispatcher(send_service=push_send),
        email=InlineEmailDispatcher(send_service=email_send),
    )
    return service, notifications, subscriptions


async def test_dispatch_pushes_to_subscription(
    clean_tables: None,
    async_session: AsyncSession,
    seed_user: Callable[..., UUID],
    seed_push_subscription: Callable[..., UUID],
) -> None:
    user_id = seed_user()
    seed_push_subscription(user_id=user_id, endpoint="https://push/device-1")
    web_push = InMemoryWebPushClient()
    service, notifications, _ = _dispatch_service(async_session, web_push)

    result = await service.dispatch(
        user_id=user_id,
        type="offer_accepted",
        title="Offer accepted",
        body="Accepted.",
        channels={"push"},
    )
    await async_session.commit()

    assert [p.endpoint for p in web_push.sent] == ["https://push/device-1"]
    push_row = await notifications.get_by_id(result.push_id)  # type: ignore[arg-type]
    assert push_row is not None and push_row.sent_at is not None


async def test_dispatch_prunes_expired_subscription(
    clean_tables: None,
    async_session: AsyncSession,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_push_subscription: Callable[..., UUID],
) -> None:
    user_id = seed_user()
    seed_push_subscription(user_id=user_id, endpoint="https://push/dead")
    web_push = InMemoryWebPushClient(gone_next=True)
    service, notifications, _ = _dispatch_service(async_session, web_push)

    result = await service.dispatch(
        user_id=user_id, type="offer_accepted", body="Accepted.", channels={"push"}
    )
    await async_session.commit()

    assert web_push.sent == []  # nothing delivered
    push_row = await notifications.get_by_id(result.push_id)  # type: ignore[arg-type]
    assert push_row is not None and push_row.sent_at is None  # unsent
    assert _active_sub_count(db_engine, user_id) == 0  # dead subscription pruned
