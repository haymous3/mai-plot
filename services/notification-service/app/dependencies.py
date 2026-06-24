"""FastAPI dependency wiring for notification-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ses_email import EmailClient, build_email_client
from app.adapters.termii import TermiiClient, build_termii_client
from app.adapters.web_push import WebPushClient, build_web_push_client
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.notification_repo import NotificationRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.repositories.user_repo import UserRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.dispatch_factory import build_dispatch_service
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.notification_centre import NotificationCentreService
from app.services.notification_dispatch import NotificationDispatchService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# One client per process — the Termii (httpx), Web Push, and SES (boto3) clients
# pool/reuse under the hood, so they are built once rather than per request.
_termii: TermiiClient | None = None
_web_push: WebPushClient | None = None
_email_client: EmailClient | None = None


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _notification_repo(session: SessionDep) -> NotificationRepository:
    return NotificationRepository(session)


def _user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def _push_subscription_repo(session: SessionDep) -> PushSubscriptionRepository:
    return PushSubscriptionRepository(session)


def get_push_subscription_repo(
    repo: Annotated[PushSubscriptionRepository, Depends(_push_subscription_repo)],
) -> PushSubscriptionRepository:
    return repo


def get_termii(settings: SettingsDep) -> TermiiClient:
    global _termii
    if _termii is None:
        _termii = build_termii_client(
            use_fake=settings.termii_use_fake,
            api_key=settings.termii_api_key,
            sender_id=settings.termii_sender_id,
            base_url=settings.termii_base_url,
            timeout_seconds=settings.termii_timeout_seconds,
        )
    return _termii


def get_web_push(settings: SettingsDep) -> WebPushClient:
    global _web_push
    if _web_push is None:
        _web_push = build_web_push_client(
            use_fake=settings.web_push_use_fake,
            vapid_private_key=settings.vapid_private_key,
            vapid_subject=settings.vapid_subject,
            ttl=settings.push_ttl_seconds,
        )
    return _web_push


def get_email_client(settings: SettingsDep) -> EmailClient:
    global _email_client
    if _email_client is None:
        _email_client = build_email_client(
            use_fake=settings.ses_use_fake,
            from_email=settings.ses_from_email,
            region=settings.ses_region,
            endpoint_url=settings.ses_endpoint_url,
        )
    return _email_client


def get_notification_centre_service(
    notifications: Annotated[NotificationRepository, Depends(_notification_repo)],
) -> NotificationCentreService:
    return NotificationCentreService(notifications=notifications)


def get_notification_dispatch_service(
    settings: SettingsDep,
    notifications: Annotated[NotificationRepository, Depends(_notification_repo)],
    users: Annotated[UserRepository, Depends(_user_repo)],
    subscriptions: Annotated[PushSubscriptionRepository, Depends(_push_subscription_repo)],
    termii: Annotated[TermiiClient, Depends(get_termii)],
    web_push: Annotated[WebPushClient, Depends(get_web_push)],
    email_client: Annotated[EmailClient, Depends(get_email_client)],
) -> NotificationDispatchService:
    """The dispatch seam used on the request path. Channel dispatchers run inline
    in dev/CI (no broker) or enqueue Celery tasks in production (sms_via_celery /
    push_via_celery / email_via_celery). Process-singleton clients are reused for
    connection pooling."""
    return build_dispatch_service(
        settings=settings,
        notifications=notifications,
        users=users,
        subscriptions=subscriptions,
        termii=termii,
        web_push=web_push,
        email_client=email_client,
    )


async def get_current_user(
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Validate the bearer access token and return the caller's identity."""
    token = parse_bearer(authorization)
    try:
        claims = verifier.decode_access(token)
    except TokenExpired as exc:
        raise AuthenticationError("TOKEN_EXPIRED", "Access token has expired.") from exc
    except TokenInvalid as exc:
        raise AuthenticationError("TOKEN_INVALID", "Access token is invalid.") from exc

    if claims.role is None:
        raise AuthenticationError("TOKEN_INVALID", "Access token is missing a role.")
    return CurrentUser(user_id=claims.user_id, role=claims.role)
