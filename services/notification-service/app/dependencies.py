"""FastAPI dependency wiring for notification-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.notification_repo import NotificationRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.notification_centre import NotificationCentreService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _notification_repo(session: SessionDep) -> NotificationRepository:
    return NotificationRepository(session)


def get_notification_centre_service(
    notifications: Annotated[NotificationRepository, Depends(_notification_repo)],
) -> NotificationCentreService:
    return NotificationCentreService(notifications=notifications)


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
