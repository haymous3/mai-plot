"""Serve a verified document with a per-viewer watermark.

GET /documents/{id}/view: only a VERIFIED document is served, only to an
authenticated caller, and only after a buyer-name + timestamp overlay is
applied (CLAUDE.md). The S3 object is never exposed — the API streams the
watermarked bytes itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.adapters.watermark import Watermarker
from app.repositories.document_repo import DocumentRepository, ViewDoc
from app.repositories.listing_repo import ListingRepository
from app.repositories.user_repo import UserRepository
from app.security import CurrentUser

logger = logging.getLogger(__name__)

_CONTENT_TYPE_BY_EXT = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}


class DocumentViewError(RuntimeError):
    pass


class DocumentNotFound(DocumentViewError):
    pass


class DocumentNotViewable(DocumentViewError):
    """The document is not verified, so it cannot be served to a buyer."""


class DocumentStorageUnavailable(DocumentViewError):
    """The document bytes could not be fetched."""


@dataclass(frozen=True)
class RenderedDocument:
    content: bytes
    content_type: str


def _content_type_for(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    return _CONTENT_TYPE_BY_EXT.get(ext, "application/octet-stream")


class DocumentViewService:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        listings: ListingRepository,
        users: UserRepository,
        storage: DocumentStorage,
        watermarker: Watermarker,
    ) -> None:
        self._documents = documents
        self._listings = listings
        self._users = users
        self._storage = storage
        self._watermarker = watermarker

    async def render(self, *, document_id: UUID, viewer: CurrentUser) -> RenderedDocument:
        doc = await self._documents.get_view(document_id)
        if doc is None:
            raise DocumentNotFound()

        # Entity-level authorization (prevents IDOR): only the listing's owner,
        # an admin, or a buyer with an active offer may view the document. An
        # unauthorized caller gets 404 — the endpoint never confirms the
        # document exists to someone with no relationship to the listing.
        if not await self._is_authorized(doc, viewer):
            raise DocumentNotFound()

        if doc.verification_status != "verified":
            # Unverified documents are never served (even to authorized callers).
            raise DocumentNotViewable()

        try:
            raw = await self._storage.get(doc.s3_key)
        except DocumentStorageError as exc:
            logger.error("document.view.storage_unavailable", extra={"key": doc.s3_key})
            raise DocumentStorageUnavailable() from exc

        name = await self._users.get_display_name(viewer.user_id) or str(viewer.user_id)
        overlay = f"{name} • {datetime.now(UTC).isoformat()}"
        content_type = _content_type_for(doc.s3_key)
        watermarked = self._watermarker.apply(data=raw, content_type=content_type, overlay=overlay)
        return RenderedDocument(content=watermarked, content_type=content_type)

    async def _is_authorized(self, doc: ViewDoc, viewer: CurrentUser) -> bool:
        """The listing owner, an admin, or a buyer with an active offer on the
        listing may view its documents."""
        if viewer.role == "admin" or viewer.user_id == doc.seller_id:
            return True
        return await self._listings.has_active_offer(
            listing_id=doc.listing_id, buyer_id=viewer.user_id
        )
