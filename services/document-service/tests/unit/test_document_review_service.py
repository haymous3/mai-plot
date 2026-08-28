"""DocumentReviewService — verify/reject, validation, audit, source dispatch."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.document_repo import DocStatus
from app.repositories.user_document_repo import UserDocStatus
from app.schemas.document import DocSource
from app.security import CurrentUser
from app.services.document_review import (
    DocumentNotFound,
    DocumentNotPending,
    DocumentReviewService,
    NotesRequired,
)

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")


class _StubRepo:
    def __init__(self, status: DocStatus | UserDocStatus | None) -> None:
        self._status = status
        self.set_call: dict[str, object] | None = None

    async def get_status(self, document_id: UUID) -> DocStatus | UserDocStatus | None:
        return self._status

    async def set_verification(
        self, document_id: UUID, *, status: str, verified_by_user_id: UUID, notes: str | None
    ) -> None:
        self.set_call = {"status": status, "verified_by": verified_by_user_id, "notes": notes}


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


def _pending() -> DocStatus:
    return DocStatus(listing_id=uuid4(), verification_status="pending")


def _service(
    repo: _StubRepo, user_repo: _StubRepo | None = None
) -> tuple[DocumentReviewService, _StubAudit]:
    audit = _StubAudit()
    service = DocumentReviewService(
        documents=repo,  # type: ignore[arg-type]
        user_documents=(user_repo or _StubRepo(None)),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
    )
    return service, audit


@pytest.mark.asyncio
async def test_verify_marks_verified_and_audits() -> None:
    repo = _StubRepo(_pending())
    svc, audit = _service(repo)
    result = await svc.review(document_id=uuid4(), admin=_ADMIN, action="verify", notes=None)

    assert result.verification_status == "verified"
    assert repo.set_call is not None
    assert repo.set_call["status"] == "verified"
    assert repo.set_call["verified_by"] == _ADMIN.user_id
    assert audit.records[0]["action"] == "document.verified"


@pytest.mark.asyncio
async def test_reject_requires_notes() -> None:
    repo = _StubRepo(_pending())
    svc, audit = _service(repo)
    with pytest.raises(NotesRequired):
        await svc.review(document_id=uuid4(), admin=_ADMIN, action="reject", notes="  ")
    assert repo.set_call is None
    assert audit.records == []


@pytest.mark.asyncio
async def test_reject_marks_failed_with_notes() -> None:
    repo = _StubRepo(_pending())
    svc, audit = _service(repo)
    result = await svc.review(
        document_id=uuid4(), admin=_ADMIN, action="reject", notes="blurry scan"
    )
    assert result.verification_status == "failed"
    assert repo.set_call is not None
    assert repo.set_call["status"] == "failed"
    assert repo.set_call["notes"] == "blurry scan"
    assert audit.records[0]["action"] == "document.failed"


@pytest.mark.asyncio
async def test_already_decided_cannot_be_reviewed() -> None:
    repo = _StubRepo(DocStatus(listing_id=uuid4(), verification_status="verified"))
    svc, _ = _service(repo)
    with pytest.raises(DocumentNotPending):
        await svc.review(document_id=uuid4(), admin=_ADMIN, action="verify", notes=None)
    assert repo.set_call is None


@pytest.mark.asyncio
async def test_missing_document_raises() -> None:
    svc, _ = _service(_StubRepo(None))
    with pytest.raises(DocumentNotFound):
        await svc.review(document_id=uuid4(), admin=_ADMIN, action="verify", notes=None)


# --------------------------------------------------------------------------
# SCRUM-192 — under_review is reviewable
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_under_review_document_can_be_verified() -> None:
    """OCR escalates to under_review; a human must be able to act on that.

    Before SCRUM-192 this raised DocumentNotPending, so the documents the OCR
    pipeline flagged FOR a human were exactly the ones no human could decide.
    """
    repo = _StubRepo(DocStatus(listing_id=uuid4(), verification_status="under_review"))
    svc, audit = _service(repo)
    result = await svc.review(document_id=uuid4(), admin=_ADMIN, action="verify", notes=None)

    assert result.verification_status == "verified"
    assert repo.set_call is not None
    assert repo.set_call["status"] == "verified"
    assert audit.records[0]["action"] == "document.verified"


@pytest.mark.asyncio
async def test_under_review_document_can_be_rejected() -> None:
    repo = _StubRepo(DocStatus(listing_id=uuid4(), verification_status="under_review"))
    svc, _ = _service(repo)
    result = await svc.review(document_id=uuid4(), admin=_ADMIN, action="reject", notes="illegible")
    assert result.verification_status == "failed"


@pytest.mark.asyncio
async def test_audit_records_the_real_previous_status_not_a_constant() -> None:
    """The audit log is append-only, so a hard-coded old_value is a false record."""
    repo = _StubRepo(DocStatus(listing_id=uuid4(), verification_status="under_review"))
    svc, audit = _service(repo)
    await svc.review(document_id=uuid4(), admin=_ADMIN, action="verify", notes=None)

    assert audit.records[0]["old_value"] == {
        "verification_status": "under_review",
        "source": "listing",
    }


# --------------------------------------------------------------------------
# SCRUM-192 — source dispatch
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personal_source_writes_to_the_user_documents_repo_only() -> None:
    listing_repo = _StubRepo(_pending())
    user_repo = _StubRepo(UserDocStatus(user_id=uuid4(), verification_status="pending"))
    svc, audit = _service(listing_repo, user_repo)

    result = await svc.review(
        document_id=uuid4(), admin=_ADMIN, action="verify", notes=None, source="personal"
    )

    assert result.source == "personal"
    assert user_repo.set_call is not None
    assert user_repo.set_call["status"] == "verified"
    # The listing table must not be touched. Nothing stops the same uuid
    # existing in both tables, and a stray write would decide someone else's
    # document on the strength of an id collision.
    assert listing_repo.set_call is None
    assert audit.records[0]["new_value"] == {
        "verification_status": "verified",
        "notes": None,
        "source": "personal",
    }


@pytest.mark.asyncio
async def test_default_source_is_listing() -> None:
    listing_repo = _StubRepo(_pending())
    user_repo = _StubRepo(UserDocStatus(user_id=uuid4(), verification_status="pending"))
    svc, _ = _service(listing_repo, user_repo)

    result = await svc.review(document_id=uuid4(), admin=_ADMIN, action="verify", notes=None)

    assert result.source == "listing"
    assert listing_repo.set_call is not None
    assert user_repo.set_call is None


@pytest.mark.asyncio
async def test_personal_document_missing_is_not_masked_by_the_listing_table() -> None:
    """An id absent from user_documents must 404 rather than fall through to
    the listing table, which would happily answer for a different document."""
    listing_repo = _StubRepo(_pending())
    user_repo = _StubRepo(None)
    svc, _ = _service(listing_repo, user_repo)

    with pytest.raises(DocumentNotFound):
        await svc.review(
            document_id=uuid4(), admin=_ADMIN, action="verify", notes=None, source="personal"
        )
    assert listing_repo.set_call is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["listing", "personal"])
async def test_rejection_notes_required_for_both_sources(source: DocSource) -> None:
    listing_repo = _StubRepo(_pending())
    user_repo = _StubRepo(UserDocStatus(user_id=uuid4(), verification_status="pending"))
    svc, _ = _service(listing_repo, user_repo)

    with pytest.raises(NotesRequired):
        await svc.review(
            document_id=uuid4(), admin=_ADMIN, action="reject", notes=None, source=source
        )
