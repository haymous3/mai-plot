"""Serve a PoA document to the legal team for review (SCRUM-61).

The PoA document lives in the PRIVATE bucket; only the legal team may view it,
and only via this server-side fetch (never a public/pre-signed URL handed to a
browser). Every access is written to the append-only audit_log — these are
sensitive legal documents, so the access trail matters.
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
from app.repositories.user_repo import UserRepository
from app.security import CurrentUser

logger = logging.getLogger(__name__)


class PoaDocumentError(RuntimeError):
    pass


class PoaDocumentNotFound(PoaDocumentError):
    """No live user with that id, or they have no PoA document on file."""


class PoaDocumentUnavailable(PoaDocumentError):
    """The storage backend failed — a retryable condition."""


@dataclass(frozen=True)
class PoaDocument:
    content: bytes
    content_type: str


def _content_type_for(key: str) -> str:
    lowered = key.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    return "application/octet-stream"


class PoaDocumentService:
    def __init__(
        self,
        *,
        users: UserRepository,
        audit: AuditLogRepository,
        storage: DocumentStorage,
    ) -> None:
        self._users = users
        self._audit = audit
        self._storage = storage

    async def get_document(
        self,
        *,
        user_id: UUID,
        viewer: CurrentUser,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PoaDocument:
        key = await self._users.get_poa_document_key(user_id)
        if key is None:
            raise PoaDocumentNotFound()

        try:
            content = await self._storage.get(key)
        except DocumentObjectMissing as exc:
            raise PoaDocumentNotFound() from exc
        except DocumentStorageError as exc:
            logger.error("poa.document.storage_unavailable", extra={"user_id": str(user_id)})
            raise PoaDocumentUnavailable() from exc

        # Sensitive legal document — record who viewed whose PoA, and when.
        await self._audit.record(
            actor_id=viewer.user_id,
            actor_role=viewer.role,
            action="poa.document_viewed",
            entity_type="user",
            entity_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return PoaDocument(content=content, content_type=_content_type_for(key))
