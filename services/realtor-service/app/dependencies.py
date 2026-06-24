"""FastAPI dependency wiring for realtor-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.document_storage import DocumentStorage, build_document_storage
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.commission_repo import CommissionRepository
from app.repositories.inspection_repo import InspectionRepository
from app.repositories.realtor_repo import RealtorRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import AdminAccessError, AuthenticationError, CurrentUser, parse_bearer
from app.services.commission_service import CommissionService
from app.services.credential_service import CredentialAccessService
from app.services.inspection_notifier import InspectionNotifier, build_inspection_notifier
from app.services.inspection_service import InspectionService
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.realtor_notifier import RealtorNotifier, build_realtor_notifier
from app.services.realtor_onboarding import RealtorOnboardingService
from app.services.realtor_review import RealtorReviewService
from app.services.report_service import ReportService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Process-singletons — the S3 client and the Celery producers build pooled
# connections reused across requests rather than rebuilt each call.
_storage: DocumentStorage | None = None
_notifier: RealtorNotifier | None = None
_inspection_notifier: InspectionNotifier | None = None


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _realtor_repo(session: SessionDep) -> RealtorRepository:
    return RealtorRepository(session)


def _audit_repo(session: SessionDep) -> AuditLogRepository:
    return AuditLogRepository(session)


def get_storage(settings: SettingsDep) -> DocumentStorage:
    global _storage
    if _storage is None:
        _storage = build_document_storage(
            use_fake=settings.gov_id_storage_use_fake,
            bucket=settings.gov_id_s3_bucket,
            region=settings.gov_id_s3_region,
            endpoint_url=settings.gov_id_s3_endpoint_url,
        )
    return _storage


def get_realtor_notifier(settings: SettingsDep) -> RealtorNotifier:
    global _notifier
    if _notifier is None:
        _notifier = build_realtor_notifier(
            enabled=settings.notifications_enabled,
            broker_url=settings.celery_broker_url,
        )
    return _notifier


def get_onboarding_service(
    settings: SettingsDep,
    realtors: Annotated[RealtorRepository, Depends(_realtor_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    storage: Annotated[DocumentStorage, Depends(get_storage)],
) -> RealtorOnboardingService:
    return RealtorOnboardingService(
        realtors=realtors,
        audit=audit,
        storage=storage,
        max_upload_bytes=settings.gov_id_max_upload_bytes,
    )


def get_review_service(
    realtors: Annotated[RealtorRepository, Depends(_realtor_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    notifier: Annotated[RealtorNotifier, Depends(get_realtor_notifier)],
) -> RealtorReviewService:
    return RealtorReviewService(realtors=realtors, audit=audit, notifier=notifier)


def get_realtor_repo(
    repo: Annotated[RealtorRepository, Depends(_realtor_repo)],
) -> RealtorRepository:
    return repo


def get_credential_service(
    settings: SettingsDep,
    realtors: Annotated[RealtorRepository, Depends(_realtor_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    storage: Annotated[DocumentStorage, Depends(get_storage)],
) -> CredentialAccessService:
    return CredentialAccessService(
        realtors=realtors,
        audit=audit,
        storage=storage,
        presign_ttl_seconds=settings.gov_id_presign_ttl_seconds,
    )


def _inspection_repo(session: SessionDep) -> InspectionRepository:
    return InspectionRepository(session)


def _transaction_repo(session: SessionDep) -> TransactionRepository:
    return TransactionRepository(session)


def _commission_repo(session: SessionDep) -> CommissionRepository:
    return CommissionRepository(session)


def get_commission_service(
    settings: SettingsDep,
    commissions: Annotated[CommissionRepository, Depends(_commission_repo)],
) -> CommissionService:
    return CommissionService(
        commissions=commissions,
        rate_bps=settings.commission_rate_bps,
        available_business_days=settings.commission_available_business_days,
    )


def get_inspection_notifier(settings: SettingsDep) -> InspectionNotifier:
    global _inspection_notifier
    if _inspection_notifier is None:
        _inspection_notifier = build_inspection_notifier(
            enabled=settings.notifications_enabled,
            broker_url=settings.celery_broker_url,
        )
    return _inspection_notifier


def get_inspection_service(
    settings: SettingsDep,
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    realtors: Annotated[RealtorRepository, Depends(_realtor_repo)],
    inspections: Annotated[InspectionRepository, Depends(_inspection_repo)],
    notifier: Annotated[InspectionNotifier, Depends(get_inspection_notifier)],
) -> InspectionService:
    return InspectionService(
        transactions=transactions,
        realtors=realtors,
        inspections=inspections,
        notifier=notifier,
        radius_meters=settings.inspection_radius_meters,
        assignment_window_hours=settings.inspection_window_hours,
    )


def get_report_service(
    settings: SettingsDep,
    inspections: Annotated[InspectionRepository, Depends(_inspection_repo)],
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    storage: Annotated[DocumentStorage, Depends(get_storage)],
) -> ReportService:
    return ReportService(
        inspections=inspections,
        transactions=transactions,
        audit=audit,
        storage=storage,
        gps_radius_meters=settings.inspection_gps_radius_meters,
        min_photos=settings.inspection_min_photos,
        photo_max_bytes=settings.inspection_photo_max_bytes,
        presign_ttl_seconds=settings.gov_id_presign_ttl_seconds,
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
