"""Admin document verification (POST /admin/documents/{id}/review).

The legal team verifies a pending document (-> verified) or rejects it
(-> failed, with a required reason). Every decision is a Document state
change, so it is written to the append-only audit_log (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_repo import DocumentRepository
from app.security import CurrentUser


class ReviewError(RuntimeError):
    pass


class DocumentNotFound(ReviewError):
    pass


class DocumentNotPending(ReviewError):
    """Only a pending document can be reviewed."""


class NotesRequired(ReviewError):
    """A rejection must include notes."""


@dataclass(frozen=True)
class ReviewResult:
    document_id: UUID
    verification_status: str


class DocumentReviewService:
    def __init__(self, *, documents: DocumentRepository, audit: AuditLogRepository) -> None:
        self._documents = documents
        self._audit = audit

    async def review(
        self,
        *,
        document_id: UUID,
        admin: CurrentUser,
        action: str,
        notes: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ReviewResult:
        current = await self._documents.get_status(document_id)
        if current is None:
            raise DocumentNotFound()
        if current.verification_status != "pending":
            raise DocumentNotPending()

        new_status: str
        reason: str | None
        if action == "reject":
            if not notes or not notes.strip():
                raise NotesRequired()
            new_status, reason = "failed", notes.strip()
        else:  # verify
            new_status, reason = "verified", (notes.strip() if notes else None)

        await self._documents.set_verification(
            document_id, status=new_status, verified_by_user_id=admin.user_id, notes=reason
        )
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role="admin",
            action=f"document.{new_status}",
            entity_type="document",
            entity_id=document_id,
            old_value={"verification_status": "pending"},
            new_value={"verification_status": new_status, "notes": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ReviewResult(document_id=document_id, verification_status=new_status)
