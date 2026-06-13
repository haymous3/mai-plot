"""DocumentReviewService — verify/reject, validation, audit."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.document_repo import DocStatus
from app.security import CurrentUser
from app.services.document_review import (
    DocumentNotFound,
    DocumentNotPending,
    DocumentReviewService,
    NotesRequired,
)

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")


class _StubRepo:
    def __init__(self, status: DocStatus | None) -> None:
        self._status = status
        self.set_call: dict[str, object] | None = None

    async def get_status(self, document_id: UUID) -> DocStatus | None:
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


def _service(repo: _StubRepo) -> tuple[DocumentReviewService, _StubAudit]:
    audit = _StubAudit()
    return DocumentReviewService(documents=repo, audit=audit), audit  # type: ignore[arg-type]


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
async def test_non_pending_cannot_be_reviewed() -> None:
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
