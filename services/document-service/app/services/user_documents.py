"""Personal-document upload / listing / removal — My Documents (SCRUM-188).

Modelled on `loan_document_upload.py`: magic-byte validation, PRIVATE bucket,
short-TTL pre-signed URLs, no OCR and no watermark. These are the user's OWN
documents being served back to the person who uploaded them, so there is no
buyer-name watermark to apply (that exists to trace a title document leaked by
a buyer, which is a different situation entirely).

Authorisation is by ownership on every path, enforced in SQL — see
`UserDocumentRepository.get_owned`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.user_document_repo import UserDocumentRepository
from app.services.document import (
    InvalidDocument,
    build_user_document_key,
    detect_document_type,
    validate_size,
)

logger = logging.getLogger(__name__)

# The sidebar taxonomy. Mirrors the CHECK constraint in migration 0003 — a
# value outside this set is rejected before it can reach the database, so the
# constraint is a backstop rather than the error path the user sees.
CATEGORIES = ("identity", "financial", "property", "other")

# Every status the table can hold, so a count of zero still reports its key.
# Without this the stat cards would omit "Rejected: 0" rather than showing it.
STATUSES = ("pending", "verified", "failed", "under_review")


class UserDocumentError(RuntimeError):
    pass


class UserDocumentNotFound(UserDocumentError):
    """No live document with that id owned by this caller."""


class UserDocumentStorageUnavailable(UserDocumentError):
    """The storage backend failed — retryable."""


@dataclass(frozen=True)
class UserDocumentView:
    id: UUID
    category: str
    file_name: str
    size_bytes: int
    content_type: str
    verification_status: str
    verification_notes: str | None
    created_at: datetime


@dataclass(frozen=True)
class UserDocumentSummary:
    documents: list[UserDocumentView]
    category_counts: dict[str, int]
    status_counts: dict[str, int]
    total: int


class UserDocumentService:
    def __init__(
        self,
        *,
        documents: UserDocumentRepository,
        storage: DocumentStorage,
        max_bytes: int,
        presign_ttl_seconds: int,
    ) -> None:
        self._documents = documents
        self._storage = storage
        self._max_bytes = max_bytes
        self._presign_ttl = presign_ttl_seconds

    async def upload(
        self,
        *,
        user_id: UUID,
        category: str,
        file_name: str,
        data: bytes,
    ) -> UUID:
        """Validate and store one personal document. Returns its id.

        Validation runs before anything is written, and the DB row is only
        inserted after the object is safely in the bucket — so a storage
        failure cannot leave a row pointing at bytes that were never stored.
        """
        if category not in CATEGORIES:
            raise InvalidDocument(
                "DOCUMENT_CATEGORY_INVALID",
                f"Category must be one of: {', '.join(CATEGORIES)}.",
            )
        validate_size(data, max_bytes=self._max_bytes)
        # allow_png: the design's own copy says "PDF, JPG, PNG (max 10MB)".
        content_type, extension = detect_document_type(data, allow_png=True)

        key = build_user_document_key(user_id, extension=extension)
        try:
            await self._storage.put(key=key, data=data, content_type=content_type)
        except DocumentStorageError as exc:
            # Never echo the exception payload — it can carry request content.
            logger.error(
                "user_document.upload.storage_unavailable",
                extra={"user_id": str(user_id)},
            )
            raise UserDocumentStorageUnavailable() from exc

        return await self._documents.insert_document(
            user_id=user_id,
            category=category,
            file_name=_safe_file_name(file_name, extension=extension),
            size_bytes=len(data),
            content_type=content_type,
            s3_key=key,
        )

    async def summary(self, *, user_id: UUID, category: str | None = None) -> UserDocumentSummary:
        """The list plus the counts the page's cards and sidebar need.

        Counts always cover ALL of the user's documents, even when the list is
        filtered to one category — otherwise selecting "Identity" would zero
        every other tab's badge and the stat cards along with it.
        """
        if category is not None and category not in CATEGORIES:
            raise InvalidDocument(
                "DOCUMENT_CATEGORY_INVALID",
                f"Category must be one of: {', '.join(CATEGORIES)}.",
            )

        rows = await self._documents.list_for_user(user_id, category=category)
        by_category = {c: 0 for c in CATEGORIES}
        for cat_row in await self._documents.count_by_category(user_id):
            by_category[cat_row.category] = cat_row.count
        by_status = {s: 0 for s in STATUSES}
        for status_row in await self._documents.count_by_status(user_id):
            by_status[status_row.verification_status] = status_row.count

        return UserDocumentSummary(
            documents=[
                UserDocumentView(
                    id=r.id,
                    category=r.category,
                    file_name=r.file_name,
                    size_bytes=r.size_bytes,
                    content_type=r.content_type,
                    verification_status=r.verification_status,
                    verification_notes=r.verification_notes,
                    created_at=r.created_at,
                )
                for r in rows
            ],
            category_counts=by_category,
            status_counts=by_status,
            total=sum(by_category.values()),
        )

    async def view_url(self, *, document_id: UUID, user_id: UUID) -> str:
        """A short-TTL pre-signed URL for one of the caller's own documents.

        The bucket is private (CLAUDE.md §4), so this is the only way the file
        reaches a browser. No watermark: the viewer is the owner.
        """
        row = await self._documents.get_owned(document_id, user_id=user_id)
        if row is None:
            raise UserDocumentNotFound()
        return self._storage.presigned_get_url(row.s3_key, expires_seconds=self._presign_ttl)

    async def delete(self, *, document_id: UUID, user_id: UUID) -> None:
        """Soft-delete one of the caller's documents.

        Soft, and the S3 object is deliberately LEFT in place. A verified
        document may already be evidence attached to a KYC decision taken on
        the bank's behalf (AMLON, §9); the row disappearing from the user's
        list is what they asked for, and destroying the underlying bytes is a
        separate, deliberate erasure step rather than a side effect of tidying
        a list. Contrast the profile photo, which has no such retention basis
        and IS destroyed on account deletion.
        """
        if not await self._documents.soft_delete(document_id, user_id=user_id):
            raise UserDocumentNotFound()


def _safe_file_name(raw: str, *, extension: str) -> str:
    """A display name safe to store and echo back.

    The client controls this string, and it is rendered in a list, so it is
    stripped of path separators (a browser can send "../../etc/passwd" as a
    filename) and truncated. It is ONLY ever a label — the object is addressed
    by the server-generated uuid key, never by this — so it needs no further
    sanitising beyond keeping it short and path-free.
    """
    cleaned = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not cleaned:
        cleaned = f"document.{extension}"
    return cleaned[:255]
