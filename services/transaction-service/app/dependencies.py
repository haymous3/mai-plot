"""FastAPI dependency wiring for transaction-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.paystack_charge import PaystackChargeClient, build_paystack_charge_client
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.offer_repo import OfferRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.wallet_repo import WalletRepository
from app.security import AdminAccessError, AuthenticationError, CurrentUser, parse_bearer
from app.services.buyer_deals import BuyerDealsService
from app.services.deposit import DepositService
from app.services.escrow_ledger import EscrowLedgerService
from app.services.financing_summary import FinancingSummaryService
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.offer_service import OfferService
from app.services.paystack_webhook import PaystackWebhookService
from app.services.seller_notifier import SellerNotifier, build_seller_notifier
from app.services.seller_offers import SellerOffersService
from app.services.transaction_status import TransactionStatusService
from app.services.wallet import WalletService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _offer_repo(session: SessionDep) -> OfferRepository:
    return OfferRepository(session)


def get_seller_offers_service(
    offers: Annotated[OfferRepository, Depends(_offer_repo)],
) -> SellerOffersService:
    return SellerOffersService(offers=offers)


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


def _payment_repo(session: SessionDep) -> PaymentEventRepository:
    return PaymentEventRepository(session)


# Process-singleton Paystack charge client (the real one holds an HTTP client).
_charge_client: PaystackChargeClient | None = None


def get_charge_client(settings: SettingsDep) -> PaystackChargeClient:
    global _charge_client
    if _charge_client is None:
        _charge_client = build_paystack_charge_client(
            enabled=settings.paystack_enabled,
            secret_key=settings.paystack_secret_key,
            base_url=settings.paystack_base_url,
        )
    return _charge_client


def get_deposit_service(
    settings: SettingsDep,
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    payments: Annotated[PaymentEventRepository, Depends(_payment_repo)],
    charge_client: Annotated[PaystackChargeClient, Depends(get_charge_client)],
) -> DepositService:
    return DepositService(
        transactions=transactions,
        payments=payments,
        charge_client=charge_client,
        callback_url=settings.paystack_callback_url,
    )


def get_webhook_service(
    settings: SettingsDep,
    payments: Annotated[PaymentEventRepository, Depends(_payment_repo)],
    escrow: Annotated[EscrowLedgerService, Depends(get_escrow_service)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
) -> PaystackWebhookService:
    return PaystackWebhookService(
        payments=payments,
        escrow=escrow,
        audit=audit,
        secret=settings.paystack_webhook_secret,
    )


# One seller notifier per process — the Celery producer app builds a broker
# connection pool that is reused across requests rather than rebuilt each call.
_seller_notifier: SellerNotifier | None = None


def get_seller_notifier(settings: SettingsDep) -> SellerNotifier:
    global _seller_notifier
    if _seller_notifier is None:
        _seller_notifier = build_seller_notifier(
            enabled=settings.notifications_enabled,
            broker_url=settings.celery_broker_url,
        )
    return _seller_notifier


def get_offer_service(
    offers: Annotated[OfferRepository, Depends(_offer_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    settings: SettingsDep,
    notifier: Annotated[SellerNotifier, Depends(get_seller_notifier)],
) -> OfferService:
    return OfferService(
        offers=offers,
        listings=listings,
        transactions=transactions,
        audit=audit,
        offer_expiry_hours=settings.offer_expiry_hours,
        notifier=notifier,
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


def get_financing_summary_service(
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
) -> FinancingSummaryService:
    return FinancingSummaryService(transactions=transactions, listings=listings)


def get_buyer_deals_service(
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
) -> BuyerDealsService:
    return BuyerDealsService(transactions=transactions)


def _wallet_repo(session: SessionDep) -> WalletRepository:
    return WalletRepository(session)


def get_wallet_service(
    wallet: Annotated[WalletRepository, Depends(_wallet_repo)],
) -> WalletService:
    return WalletService(wallet=wallet)


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
