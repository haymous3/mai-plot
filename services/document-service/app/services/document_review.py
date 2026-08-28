"""Admin document verification (POST /admin/documents/{id}/review).

The legal team verifies a pending document (-> verified) or rejects it
(-> failed, with a required reason). Every decision is a Document state
change, so it is written to the append-only audit_log (CLAUDE.md).

`source` selects which table the id refers to — `listing_documents` (the
default, and the only option before SCRUM-192) or `user_documents`. Both
repositories expose the same `get_status` / `set_verification` pair, so the
decision logic below is written once and runs for either.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_document_repo import UserDocumentRepository
from app.schemas.document import DocSource
from app.security import CurrentUser

# The states a document may be reviewed FROM.
#
# ⚠️ `under_review` is here for a reason (SCRUM-192). The OCR pipeline calls
# `flag_for_manual_review()`, which moves a document to `under_review` precisely
# because it needs a human. While this guard accepted only `pending`, those
# documents were a dead end: the queue could list them and no reviewer could
# verify or reject one. Accepting both is what makes the escalation path work.
REVIEWABLE_STATUSES = ("pending", "under_review")


class ReviewError(RuntimeError):
    pass


class DocumentNotFound(ReviewError):
    pass


class DocumentNotPending(ReviewError):
    """Already decided — only a pending or under-review document can be reviewed.

    The name and its DOCUMENT_NOT_PENDING error code predate SCRUM-192 widening
    the accepted set; both are kept because the code is a published contract.
    """


class NotesRequired(ReviewError):
    """A rejection must include notes."""


@dataclass(frozen=True)
class ReviewResult:
    document_id: UUID
    verification_status: str
    source: DocSource


class DocumentReviewService:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        user_documents: UserDocumentRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._documents = documents
        self._user_documents = user_documents
        self._audit = audit

    async def review(
        self,
        *,
        document_id: UUID,
        admin: CurrentUser,
        action: str,
        notes: str | None,
        source: DocSource = "listing",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ReviewResult:
        repo: DocumentRepository | UserDocumentRepository = (
            self._user_documents if source == "personal" else self._documents
        )

        current = await repo.get_status(document_id)
        if current is None:
            raise DocumentNotFound()
        previous_status = current.verification_status
        if previous_status not in REVIEWABLE_STATUSES:
            raise DocumentNotPending()

        new_status: str
        reason: str | None
        if action == "reject":
            if not notes or not notes.strip():
                raise NotesRequired()
            new_status, reason = "failed", notes.strip()
        else:  # verify
            new_status, reason = "verified", (notes.strip() if notes else None)

        await repo.set_verification(
            document_id, status=new_status, verified_by_user_id=admin.user_id, notes=reason
        )
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role="admin",
            action=f"document.{new_status}",
            entity_type="document",
            entity_id=document_id,
            # The REAL prior status, not a hard-coded "pending". Once
            # under_review became reviewable, a fixed value here would have
            # written a false entry into an append-only log.
            old_value={"verification_status": previous_status, "source": source},
            new_value={"verification_status": new_status, "notes": reason, "source": source},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ReviewResult(document_id=document_id, verification_status=new_status, source=source)
