"""FastAPI dependency wiring for listing-service.

Route handlers depend on the factories here; tests override them via
app.dependency_overrides. Mirrors auth-service's dependency module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.listing_repo import ListingRepository
from app.repositories.seller_repo import SellerRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.listing_create import ListingCreateService
from app.services.listing_detail import ListingDetailService
from app.services.listing_query import ListingQueryService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_redis: Redis | None = None


async def get_redis(settings: SettingsDep) -> Redis | None:
    """Lazy process-wide Redis client. Returns None if construction fails —
    the cache helper fails open against a None client, so the feed/detail
    paths still serve from Postgres."""
    global _redis
    if _redis is None:
        try:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None
    return _redis


RedisDep = Annotated["Redis | None", Depends(get_redis)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _seller_repo(session: SessionDep) -> SellerRepository:
    return SellerRepository(session)


def _listing_repo(session: SessionDep) -> ListingRepository:
    return ListingRepository(session)


def get_listing_create_service(
    sellers: Annotated[SellerRepository, Depends(_seller_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
) -> ListingCreateService:
    return ListingCreateService(sellers=sellers, listings=listings)


def get_listing_query_service(
    redis: RedisDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    settings: SettingsDep,
) -> ListingQueryService:
    return ListingQueryService(
        redis=redis, listings=listings, ttl_seconds=settings.feed_cache_ttl_seconds
    )


def get_listing_detail_service(
    redis: RedisDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    sellers: Annotated[SellerRepository, Depends(_seller_repo)],
    settings: SettingsDep,
) -> ListingDetailService:
    return ListingDetailService(
        redis=redis,
        listings=listings,
        sellers=sellers,
        ttl_seconds=settings.listing_cache_ttl_seconds,
    )


async def get_current_user(
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Validate the bearer access token and return the caller's identity.

    Raises AuthenticationError (-> 401 envelope) for a missing, malformed,
    expired, or otherwise invalid access token.
    """
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


async def get_current_user_optional(
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    """Like get_current_user but never raises — for Auth:Optional endpoints
    (feed, detail). A missing/invalid/expired token yields None (anonymous),
    so an authenticated buyer gets the loan-eligibility indicator while
    everyone else still gets the listing."""
    if not authorization:
        return None
    try:
        claims = verifier.decode_access(parse_bearer(authorization))
    except (AuthenticationError, TokenExpired, TokenInvalid):
        return None
    if claims.role is None:
        return None
    return CurrentUser(user_id=claims.user_id, role=claims.role)
