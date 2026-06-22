"""FastAPI dependency wiring for transaction-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.offer_repo import OfferRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import AdminAccessError, AuthenticationError, CurrentUser, parse_bearer
from app.services.escrow_ledger import EscrowLedgerService
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.offer_service import OfferService
from app.services.transaction_status import TransactionStatusService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _offer_repo(session: SessionDep) -> OfferRepository:
    return OfferRepository(session)


def _listing_repo(session: SessionDep) -> ListingRepository:
    return ListingRepository(session)


def _transaction_repo(session: SessionDep) -> TransactionRepository:
    return TransactionRepository(session)


def _audit_repo(session: SessionDep) -> AuditLogRepository:
    return AuditLogRepository(session)


def _escrow_repo(session: SessionDep) -> EscrowLedgerRepository:
    return EscrowLedgerRepository(session)


def get_escrow_service(
    ledger: Annotated[EscrowLedgerRepository, Depends(_escrow_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
) -> EscrowLedgerService:
    return EscrowLedgerService(ledger=ledger, audit=audit)


def get_offer_service(
    offers: Annotated[OfferRepository, Depends(_offer_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    settings: SettingsDep,
) -> OfferService:
    return OfferService(
        offers=offers,
        listings=listings,
        transactions=transactions,
        audit=audit,
        offer_expiry_hours=settings.offer_expiry_hours,
    )


def get_transaction_status_service(
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    settings: SettingsDep,
) -> TransactionStatusService:
    return TransactionStatusService(
        transactions=transactions,
        audit=audit,
        listings=listings,
        platform_fee_bps=settings.platform_fee_bps,
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


async def require_admin(
    request: Request,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    settings: SettingsDep,
) -> CurrentUser:
    """Admin gate: a valid admin JWT AND (if configured) a whitelisted IP.
    CLAUDE.md requires both; Kong enforces the IP allowlist at the edge and this
    app-level check is defence in depth. Raises AdminAccessError -> 403."""
    if caller.role != "admin":
        raise AdminAccessError("ADMIN_FORBIDDEN", "Admin access required.")
    allowlist = [ip.strip() for ip in settings.admin_ip_allowlist.split(",") if ip.strip()]
    if allowlist:
        client_ip = request.client.host if request.client else None
        if client_ip not in allowlist:
            raise AdminAccessError(
                "ADMIN_IP_FORBIDDEN", "Your IP is not permitted for admin access."
            )
    return caller
