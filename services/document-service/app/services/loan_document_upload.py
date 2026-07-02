"""Buyer loan-document upload + listing (SCRUM-131).

The onboarding wizard's step 2 (bank statement, employment letter/CAC, passport)
attaches documents to a loan. Only the loan's buyer (or an admin) may upload or
view them. Files are validated by magic bytes (PDF/JPEG/PNG), stored in the
PRIVATE bucket, and served only via short-TTL pre-signed URLs. No OCR/watermark
(these are applicant docs for the bank, not buyer-served title docs).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.loan_document_repo import LoanDocumentRepository
from app.repositories.loan_repo import LoanRepository
from app.security import CurrentUser
from app.services.document import build_loan_document_key, detect_document_type, validate_size

logger = logging.getLogger(__name__)


class LoanDocumentError(RuntimeError):
    pass


class LoanNotFound(LoanDocumentError):
    """No live loan with that id."""


class NotLoanOwner(LoanDocumentError):
    """Caller is neither the loan's buyer nor an admin."""


class LoanDocumentStorageUnavailable(LoanDocumentError):
    """The storage backend failed — retryable."""


@dataclass(frozen=True)
class LoanDocumentUploadResult:
    document_id: UUID
    verification_status: str


@dataclass(frozen=True)
class LoanDocumentView:
    id: UUID
    document_type: str
    verification_status: str
    created_at: datetime
    url: str


class LoanDocumentService:
    def __init__(
        self,
        *,
        loans: LoanRepository,
        documents: LoanDocumentRepository,
        storage: DocumentStorage,
        max_bytes: int,
        presign_ttl_seconds: int,
    ) -> None:
        self._loans = loans
        self._documents = documents
        self._storage = storage
        self._max_bytes = max_bytes
        self._presign_ttl = presign_ttl_seconds

    async def _authorise(self, loan_id: UUID, caller: CurrentUser) -> None:
        buyer_id = await self._loans.get_loan_buyer(loan_id)
        if buyer_id is None:
            raise LoanNotFound()
        if caller.role != "admin" and buyer_id != caller.user_id:
            raise NotLoanOwner()

    async def upload(
        self, *, loan_id: UUID, caller: CurrentUser, document_type: str, data: bytes
    ) -> LoanDocumentUploadResult:
        await self._authorise(loan_id, caller)

        validate_size(data, max_bytes=self._max_bytes)
        content_type, extension = detect_document_type(data, allow_png=True)

        key = build_loan_document_key(loan_id, extension=extension)
        try:
            await self._storage.put(key=key, data=data, content_type=content_type)
        except DocumentStorageError as exc:
            logger.error(
                "loan_document.upload.storage_unavailable", extra={"loan_id": str(loan_id)}
            )
            raise LoanDocumentStorageUnavailable() from exc

        document_id = await self._documents.insert_document(
            loan_id=loan_id,
            document_type=document_type,
            s3_key=key,
            uploaded_by=caller.user_id,
        )
        logger.info(
            "loan_document.upload.ok",
            extra={"loan_id": str(loan_id), "document_id": str(document_id)},
        )
        return LoanDocumentUploadResult(document_id=document_id, verification_status="pending")

    async def list_for_loan(self, *, loan_id: UUID, caller: CurrentUser) -> list[LoanDocumentView]:
        """The loan's documents with short-TTL pre-signed view URLs (buyer or
        admin). This is how the reviewing bank/admin sees the uploads."""
        await self._authorise(loan_id, caller)
        rows = await self._documents.list_for_loan(loan_id)
        return [
            LoanDocumentView(
                id=r.id,
                document_type=r.document_type,
                verification_status=r.verification_status,
                created_at=r.created_at,
                url=self._storage.presigned_get_url(r.s3_key, expires_seconds=self._presign_ttl),
            )
            for r in rows
        ]
