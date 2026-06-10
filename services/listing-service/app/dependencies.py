"""FastAPI dependency wiring for listing-service.

Route handlers depend on the factories here; tests override them via
app.dependency_overrides. Mirrors auth-service's dependency module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.listing_repo import ListingRepository
from app.repositories.seller_repo import SellerRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.listing_create import ListingCreateService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
