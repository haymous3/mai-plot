"""FastAPI dependency wiring for notification-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.termii import TermiiClient, build_termii_client
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.notification_centre import NotificationCentreService
from app.services.notification_dispatch import NotificationDispatchService
from app.services.sms_dispatch import build_sms_dispatcher
from app.services.sms_send import SmsSendService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# One Termii client per process — httpx pools connections under the hood, so the
# real client is reused across requests rather than rebuilt each time.
_termii: TermiiClient | None = None


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _notification_repo(session: SessionDep) -> NotificationRepository:
    return NotificationRepository(session)


def _user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


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


def get_notification_centre_service(
    notifications: Annotated[NotificationRepository, Depends(_notification_repo)],
) -> NotificationCentreService:
    return NotificationCentreService(notifications=notifications)


def get_notification_dispatch_service(
    settings: SettingsDep,
    notifications: Annotated[NotificationRepository, Depends(_notification_repo)],
    users: Annotated[UserRepository, Depends(_user_repo)],
    termii: Annotated[TermiiClient, Depends(get_termii)],
) -> NotificationDispatchService:
    """The dispatch seam other services call to raise a notification. In dev/CI
    the SMS dispatcher runs the send inline (no broker); in production it enqueues
    the Celery task (sms_via_celery=true)."""
    send_service = SmsSendService(notifications=notifications, users=users, termii=termii)
    sms = build_sms_dispatcher(via_celery=settings.sms_via_celery, send_service=send_service)
    return NotificationDispatchService(notifications=notifications, sms=sms)


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
