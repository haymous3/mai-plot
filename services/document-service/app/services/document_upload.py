"""Listing document upload orchestration (POST /listings/{id}/documents).

Only the owning seller (or an admin) may attach a legal document. The file is
validated server-side (PDF/JPEG magic bytes + size), stored in the PRIVATE
documents bucket, and a listing_documents row is written with
verification_status='pending' (the verification + watermarking workflow is a
later document-service slice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.document_repo import DocumentRepository
from app.repositories.listing_repo import ListingRepository
from app.security import CurrentUser
from app.services.document import build_document_key, detect_document_type, validate_size
from app.services.ocr_dispatch import OcrDispatcher

logger = logging.getLogger(__name__)


class DocumentUploadError(RuntimeError):
    pass


class ListingNotFound(DocumentUploadError):
    """No live listing with that id."""


class NotListingOwner(DocumentUploadError):
    """Caller is neither the owning seller nor an admin."""


class DocumentStorageUnavailable(DocumentUploadError):
    """The storage backend failed — a retryable condition."""


@dataclass(frozen=True)
class DocumentUploadResult:
    document_id: UUID
    verification_status: str


class DocumentUploadService:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        documents: DocumentRepository,
        storage: DocumentStorage,
        max_bytes: int,
        ocr_dispatch: OcrDispatcher | None = None,
    ) -> None:
        self._listings = listings
        self._documents = documents
        self._storage = storage
        self._max_bytes = max_bytes
        self._ocr_dispatch = ocr_dispatch

    async def upload(
        self, *, listing_id: UUID, caller: CurrentUser, document_type: str, data: bytes
    ) -> DocumentUploadResult:
        owner = await self._listings.get_listing_owner(listing_id)
        if owner is None:
            raise ListingNotFound()
        if caller.role != "admin" and owner.seller_id != caller.user_id:
            raise NotListingOwner()

        validate_size(data, max_bytes=self._max_bytes)
        content_type, extension = detect_document_type(data)

        key = build_document_key(listing_id, extension=extension)
        try:
            await self._storage.put(key=key, data=data, content_type=content_type)
        except DocumentStorageError as exc:
            logger.error(
                "document.upload.storage_unavailable", extra={"listing_id": str(listing_id)}
            )
            raise DocumentStorageUnavailable() from exc

        document_id = await self._documents.insert_document(
            listing_id=listing_id, document_type=document_type, s3_key=key
        )
        logger.info(
            "document.upload.ok",
            extra={"listing_id": str(listing_id), "document_id": str(document_id)},
        )
        # Kick off OCR off the request path (Celery in prod, inline in dev/CI).
        # Best-effort: dispatch never blocks or fails the upload.
        if self._ocr_dispatch is not None:
            await self._ocr_dispatch.enqueue(document_id)
        return DocumentUploadResult(document_id=document_id, verification_status="pending")
