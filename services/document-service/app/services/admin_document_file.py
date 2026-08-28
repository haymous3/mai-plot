"""Serve a document to a reviewer (GET /admin/documents/{id}/file, SCRUM-192).

Why this exists at all
----------------------
`GET /documents/{id}/view` refuses to serve anything whose verification_status
is not `verified` — to EVERY caller, admins included. That is correct for
buyers and sellers: an unverified document must not circulate as if it were
checked. But it left the review queue unusable, because a reviewer's whole job
is to look at a document that is not yet verified and decide. The queue endpoint
has existed since SCRUM-23 and nothing could ever open a row from it.

So this is a separate, admin-only path rather than a carve-out in the buyer
route. Loosening `document_view` would have put "is this caller an admin?"
inside the one guard that protects unverified documents from everyone else, and
a future edit to that condition would silently widen who can read them.

Modelled directly on auth-service's `PoaDocumentService` (SCRUM-61), the
closest precedent — also a legal-team review of a document that has not been
approved yet:

  * the bytes are fetched server-side and streamed; no pre-signed URL ever
    reaches the browser, so there is no link to forward or leak (§4)
  * every access is written to the append-only audit_log, because "who opened
    whose identity document, and when" is exactly what an NDPR/AMLON enquiry
    asks (§9)
  * NOT watermarked. The watermark in §4 exists to trace a document that leaves
    the platform with a BUYER; a reviewer needs to read a NIN slip or a C of O
    number cleanly, and an overlay works against that. The PoA precedent makes
    the same call. The audit entry is the accountability mechanism here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.document_storage import (
    DocumentObjectMissing,
    DocumentStorage,
    DocumentStorageError,
)
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_document_repo import UserDocumentRepository
from app.schemas.document import DocSource
from app.security import CurrentUser

logger = logging.getLogger(__name__)


class AdminDocumentFileError(RuntimeError):
    pass


class DocumentNotFound(AdminDocumentFileError):
    """No live document with that id in the table `source` names."""


class DocumentUnavailable(AdminDocumentFileError):
    """The storage backend failed — retryable, not the caller's fault."""


@dataclass(frozen=True)
class ReviewFile:
    content: bytes
    content_type: str
    file_name: str


# The only content types this route will ever put in a Content-Type header.
#
# These bytes are served `inline` from the admin's own origin, so a type the
# browser renders as ACTIVE content (text/html, image/svg+xml) would execute in
# the reviewer's session — a stored XSS with an admin as the victim.
#
# Nothing can currently store such a type: `detect_document_type()` derives it
# from MAGIC BYTES and only ever returns these three, and the client's header is
# never trusted. But that invariant lives in another module, enforced by another
# ticket, and this is the boundary where being wrong is dangerous. Anything
# outside the set degrades to octet-stream, which browsers download rather than
# render.
SERVABLE_CONTENT_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})

_FALLBACK_CONTENT_TYPE = "application/octet-stream"


def _safe_content_type(candidate: str) -> str:
    return candidate if candidate in SERVABLE_CONTENT_TYPES else _FALLBACK_CONTENT_TYPE


def _content_type_for(key: str) -> str:
    """Infer a content type from the object key.

    Only needed for listing_documents, which stores no content_type column.
    user_documents records the real one at upload and it is used directly.
    """
    lowered = key.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".png"):
        return "image/png"
    return _FALLBACK_CONTENT_TYPE


def _safe_filename(name: str) -> str:
    """Reduce an uploaded filename to something safe to quote in a header.

    `file_name` is whatever the owner's browser sent at upload (SCRUM-188), so
    it reaches here unfiltered. A `"` would close the quoted string in
    `Content-Disposition: inline; filename="..."` early and let the rest be read
    as further header parameters; a CR/LF would be header injection outright.
    Keep a conservative set and let everything else become an underscore.
    """
    cleaned = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in name.strip()).strip()
    # Leading dots would produce ".", ".." or a hidden file on the reviewer's disk.
    cleaned = cleaned.lstrip(".")
    return cleaned[:120] or "document"


class AdminDocumentFileService:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        user_documents: UserDocumentRepository,
        audit: AuditLogRepository,
        storage: DocumentStorage,
    ) -> None:
        self._documents = documents
        self._user_documents = user_documents
        self._audit = audit
        self._storage = storage

    async def get_file(
        self,
        *,
        document_id: UUID,
        viewer: CurrentUser,
        source: DocSource = "listing",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ReviewFile:
        key, content_type, file_name = await self._locate(document_id, source)

        try:
            content = await self._storage.get(key)
        except DocumentObjectMissing as exc:
            # The row exists but the object does not. That is a 404 to the
            # caller either way, and worth a log line because it means the DB
            # and the bucket have drifted.
            logger.warning(
                "admin.document.object_missing",
                extra={"document_id": str(document_id), "source": source},
            )
            raise DocumentNotFound() from exc
        except DocumentStorageError as exc:
            logger.error(
                "admin.document.storage_unavailable",
                extra={"document_id": str(document_id), "source": source},
            )
            raise DocumentUnavailable() from exc

        # Recorded AFTER a successful fetch: the audit trail should say a
        # document was actually read, not that someone asked for a key that
        # turned out to be missing.
        await self._audit.record(
            actor_id=viewer.user_id,
            actor_role=viewer.role,
            action="document.viewed_for_review",
            entity_type="document",
            entity_id=document_id,
            new_value={"source": source},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ReviewFile(content=content, content_type=content_type, file_name=file_name)

    async def _locate(self, document_id: UUID, source: DocSource) -> tuple[str, str, str]:
        """Resolve a document id to (s3_key, content_type, download name)."""
        if source == "personal":
            personal = await self._user_documents.get_for_review(document_id)
            if personal is None:
                raise DocumentNotFound()
            # The stored content_type was determined from the file's MAGIC
            # BYTES at upload (SCRUM-188), never a client-supplied header — but
            # it is still narrowed against the allowlist before it becomes a
            # response header, and the filename is stripped before it is quoted
            # into Content-Disposition.
            return (
                personal.s3_key,
                _safe_content_type(personal.content_type),
                _safe_filename(personal.file_name),
            )

        listing = await self._documents.get_view(document_id)
        if listing is None:
            raise DocumentNotFound()
        # listing_documents keeps no original filename and no content_type —
        # both are recovered from the key, whose last segment is already
        # "{document_id}.{ext}".
        return (
            listing.s3_key,
            _content_type_for(listing.s3_key),
            _safe_filename(listing.s3_key.rsplit("/", 1)[-1]),
        )
