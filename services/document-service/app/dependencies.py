"""FastAPI dependency wiring for document-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.document_storage import DocumentStorage, build_document_storage
from app.adapters.watermark import Watermarker, build_watermarker
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.user_repo import UserRepository
from app.security import AdminAccessError, AuthenticationError, CurrentUser, parse_bearer
from app.services.admin_queue import AdminQueueService
from app.services.document_review import DocumentReviewService
from app.services.document_upload import DocumentUploadService
from app.services.document_view import DocumentViewService
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_document_storage: DocumentStorage | None = None
_watermarker: Watermarker | None = None


async def get_document_storage(settings: SettingsDep) -> DocumentStorage:
    """Process-wide private document storage (fake for local/CI, real S3 in
    production)."""
    global _document_storage
    if _document_storage is None:
        _document_storage = build_document_storage(
            use_fake=settings.doc_storage_use_fake,
            bucket=settings.doc_s3_bucket,
            region=settings.doc_s3_region,
            endpoint_url=settings.doc_s3_endpoint_url,
        )
    return _document_storage


async def get_watermarker(settings: SettingsDep) -> Watermarker:
    """Process-wide watermarker (fake for local/CI, real overlay in prod)."""
    global _watermarker
    if _watermarker is None:
        _watermarker = build_watermarker(use_fake=settings.watermark_use_fake)
    return _watermarker


DocumentStorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]
WatermarkerDep = Annotated[Watermarker, Depends(get_watermarker)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _listing_repo(session: SessionDep) -> ListingRepository:
    return ListingRepository(session)


def _document_repo(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


def _audit_repo(session: SessionDep) -> AuditLogRepository:
    return AuditLogRepository(session)


def _user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_document_view_service(
    documents: Annotated[DocumentRepository, Depends(_document_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    users: Annotated[UserRepository, Depends(_user_repo)],
    storage: DocumentStorageDep,
    watermarker: WatermarkerDep,
) -> DocumentViewService:
    return DocumentViewService(
        documents=documents,
        listings=listings,
        users=users,
        storage=storage,
        watermarker=watermarker,
    )


def get_admin_queue_service(
    documents: Annotated[DocumentRepository, Depends(_document_repo)],
) -> AdminQueueService:
    return AdminQueueService(documents=documents)


def get_document_review_service(
    documents: Annotated[DocumentRepository, Depends(_document_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
) -> DocumentReviewService:
    return DocumentReviewService(documents=documents, audit=audit)


def get_document_upload_service(
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    documents: Annotated[DocumentRepository, Depends(_document_repo)],
    storage: DocumentStorageDep,
    settings: SettingsDep,
) -> DocumentUploadService:
    return DocumentUploadService(
        listings=listings,
        documents=documents,
        storage=storage,
        max_bytes=settings.max_document_bytes,
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
    """Admin (legal team) gate: admin JWT AND (if configured) a whitelisted IP.
    Kong enforces the allowlist at the edge; this is defence in depth. Raises
    AdminAccessError -> 403."""
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
