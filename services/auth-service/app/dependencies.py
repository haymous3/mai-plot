"""FastAPI dependency wiring.

Single source of truth for the object graph: how Settings becomes a
Redis client, how a session becomes a UserRepository, how those combine
into a RegistrationService. Route handlers depend on the service-level
factories below; tests override these via app.dependency_overrides.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.termii import TermiiClient, build_termii_client
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.otp_repo import OtpRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.jwt_service import JwtService, TokenExpired, TokenInvalid
from app.services.logout import LogoutService
from app.services.otp_verification import OtpVerificationService
from app.services.rate_limit import OtpRateLimiter
from app.services.registration import RegistrationService
from app.services.token_refresh import TokenRefreshService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_redis: Redis | None = None
_termii: TermiiClient | None = None


async def get_redis(settings: SettingsDep) -> Redis | None:
    """Lazy-build a process-wide Redis client.

    Returns None if construction fails — callers (rate limiter, cache
    helper) are designed to fail open against a None client. We don't
    ping on construction because that would add a startup hop per
    process and Redis failures should surface as fail-open at use time.
    """
    global _redis
    if _redis is None:
        try:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None
    return _redis


async def get_termii(settings: SettingsDep) -> TermiiClient:
    """Process-wide Termii client. The factory picks fake vs real."""
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


RedisDep = Annotated["Redis | None", Depends(get_redis)]
TermiiDep = Annotated[TermiiClient, Depends(get_termii)]


def _user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def _otp_repo(session: SessionDep) -> OtpRepository:
    return OtpRepository(session)


def _refresh_token_repo(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def _jwt_service(settings: SettingsDep) -> JwtService:
    return JwtService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_expire_minutes=settings.jwt_access_expire_minutes,
        refresh_expire_days=settings.jwt_refresh_expire_days,
    )


def _rate_limiter(redis: RedisDep, settings: SettingsDep) -> OtpRateLimiter:
    return OtpRateLimiter(redis, max_per_hour=settings.otp_rate_limit_per_hour)


def get_registration_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    rate_limiter: Annotated[OtpRateLimiter, Depends(_rate_limiter)],
    termii: TermiiDep,
    settings: SettingsDep,
) -> RegistrationService:
    return RegistrationService(
        users=users,
        otps=otps,
        rate_limiter=rate_limiter,
        termii=termii,
        otp_expire_minutes=settings.otp_expire_minutes,
    )


def get_otp_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> OtpVerificationService:
    return OtpVerificationService(
        users=users,
        otps=otps,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
    )


def get_token_refresh_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> TokenRefreshService:
    return TokenRefreshService(
        users=users,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
    )


def get_logout_service(
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> LogoutService:
    return LogoutService(refresh_tokens=refresh_tokens, jwt=jwt_service)


async def get_current_user(
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Validate the bearer access token and return the caller's identity.

    Raises AuthenticationError (-> 401 envelope) for a missing, malformed,
    expired, or otherwise invalid access token.
    """
    token = parse_bearer(authorization)
    try:
        claims = jwt_service.decode(token, expected_type="access")
    except TokenExpired as exc:
        raise AuthenticationError("TOKEN_EXPIRED", "Access token has expired.") from exc
    except TokenInvalid as exc:
        raise AuthenticationError("TOKEN_INVALID", "Access token is invalid.") from exc

    # An access token always carries a role; guard defensively so a
    # malformed-but-signed token can't yield a None role downstream.
    if claims.role is None:
        raise AuthenticationError("TOKEN_INVALID", "Access token is missing a role.")
    return CurrentUser(user_id=claims.user_id, role=claims.role)
