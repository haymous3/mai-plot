"""FastAPI dependency wiring for document-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.document_storage import DocumentStorage, build_document_storage
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.document_repo import DocumentRepository
from app.repositories.listing_repo import ListingRepository
from app.security import AuthenticationError, CurrentUser, parse_bearer
from app.services.document_upload import DocumentUploadService
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_document_storage: DocumentStorage | None = None


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


DocumentStorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _listing_repo(session: SessionDep) -> ListingRepository:
    return ListingRepository(session)


def _document_repo(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


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
