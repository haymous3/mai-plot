"""PoaUploadService with stub repos + fake storage."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.repositories.user_repo import PoaState
from app.services.poa import InvalidPoaDocument
from app.services.poa_upload import (
    PoaAlreadySubmitted,
    PoaNotEligible,
    PoaStorageUnavailable,
    PoaUploadService,
)

_PDF = b"%PDF-1.7 fake poa document"
# A PoA seller who has registered (status pre-set to 'pending') but not yet
# uploaded a document — the eligible first-upload case.
_POA_FIRST_UPLOAD = PoaState(
    role="seller",
    seller_authority_type="power_of_attorney",
    poa_verified_status="pending",
    has_document=False,
)


class _StubUserRepo:
    def __init__(self, *, state: PoaState | None = _POA_FIRST_UPLOAD) -> None:
        self._state = state
        self.set_calls: list[dict[str, object]] = []

    async def get_poa_state(self, user_id: UUID) -> PoaState | None:
        return self._state

    async def set_poa_document(self, user_id: UUID, *, s3_key: str) -> None:
        self.set_calls.append({"user_id": user_id, "s3_key": s3_key})


class _StubAuditRepo:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


def _service(
    repo: _StubUserRepo,
    audit: _StubAuditRepo,
    storage: InMemoryDocumentStorage,
    *,
    max_bytes: int = 1024,
) -> PoaUploadService:
    return PoaUploadService(
        users=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        storage=storage,
        max_upload_bytes=max_bytes,
    )


@pytest.mark.asyncio
async def test_happy_path_stores_sets_pending_and_audits() -> None:
    repo, audit, storage = _StubUserRepo(), _StubAuditRepo(), InMemoryDocumentStorage()
    user_id = uuid4()
    result = await _service(repo, audit, storage).upload(user_id=user_id, data=_PDF)

    assert result.status == "pending"
    assert result.s3_key.startswith(f"poa/{user_id}/")
    # Stored in the (fake) bucket, recorded on the user, and audited.
    assert storage.data[result.s3_key] == _PDF
    assert repo.set_calls == [{"user_id": user_id, "s3_key": result.s3_key}]
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record["action"] == "poa.uploaded"
    assert record["entity_id"] == user_id
    assert record["new_value"]["poa_verified_status"] == "pending"  # type: ignore[index]


@pytest.mark.asyncio
async def test_non_seller_not_eligible() -> None:
    repo = _StubUserRepo(
        state=PoaState(
            role="buyer",
            seller_authority_type=None,
            poa_verified_status="not_applicable",
            has_document=False,
        )
    )
    audit, storage = _StubAuditRepo(), InMemoryDocumentStorage()
    with pytest.raises(PoaNotEligible):
        await _service(repo, audit, storage).upload(user_id=uuid4(), data=_PDF)
    assert storage.objects == {}
    assert audit.records == []


@pytest.mark.asyncio
async def test_owner_seller_not_eligible() -> None:
    repo = _StubUserRepo(
        state=PoaState(
            role="seller",
            seller_authority_type="owner",
            poa_verified_status="not_applicable",
            has_document=False,
        )
    )
    with pytest.raises(PoaNotEligible):
        await _service(repo, _StubAuditRepo(), InMemoryDocumentStorage()).upload(
            user_id=uuid4(), data=_PDF
        )


@pytest.mark.asyncio
async def test_eligibility_checked_before_format() -> None:
    # Ineligible caller with a malformed file still gets PoaNotEligible.
    repo = _StubUserRepo(
        state=PoaState(
            role="buyer",
            seller_authority_type=None,
            poa_verified_status="not_applicable",
            has_document=False,
        )
    )
    with pytest.raises(PoaNotEligible):
        await _service(repo, _StubAuditRepo(), InMemoryDocumentStorage()).upload(
            user_id=uuid4(), data=b"not a pdf"
        )


@pytest.mark.parametrize("status", ["pending", "verified"])
@pytest.mark.asyncio
async def test_existing_document_conflicts(status: str) -> None:
    # A document already on file (and not rejected) blocks re-upload.
    repo = _StubUserRepo(
        state=PoaState(
            role="seller",
            seller_authority_type="power_of_attorney",
            poa_verified_status=status,
            has_document=True,
        )
    )
    storage = InMemoryDocumentStorage()
    with pytest.raises(PoaAlreadySubmitted):
        await _service(repo, _StubAuditRepo(), storage).upload(user_id=uuid4(), data=_PDF)
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_rejected_document_allows_reupload() -> None:
    repo = _StubUserRepo(
        state=PoaState(
            role="seller",
            seller_authority_type="power_of_attorney",
            poa_verified_status="rejected",
            has_document=True,
        )
    )
    result = await _service(repo, _StubAuditRepo(), InMemoryDocumentStorage()).upload(
        user_id=uuid4(), data=_PDF
    )
    assert result.status == "pending"


@pytest.mark.asyncio
async def test_invalid_document_raises_and_does_not_store() -> None:
    repo, audit, storage = _StubUserRepo(), _StubAuditRepo(), InMemoryDocumentStorage()
    with pytest.raises(InvalidPoaDocument):
        await _service(repo, audit, storage).upload(user_id=uuid4(), data=b"GIF89a not allowed")
    assert storage.objects == {}
    assert repo.set_calls == []
    assert audit.records == []


@pytest.mark.asyncio
async def test_oversize_raises() -> None:
    repo, audit, storage = _StubUserRepo(), _StubAuditRepo(), InMemoryDocumentStorage()
    with pytest.raises(InvalidPoaDocument) as exc:
        await _service(repo, audit, storage, max_bytes=8).upload(user_id=uuid4(), data=_PDF)
    assert exc.value.code == "POA_DOCUMENT_TOO_LARGE"
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_storage_failure_is_unavailable_and_skips_db() -> None:
    repo, audit = _StubUserRepo(), _StubAuditRepo()
    storage = InMemoryDocumentStorage(fail_next=True)
    with pytest.raises(PoaStorageUnavailable):
        await _service(repo, audit, storage).upload(user_id=uuid4(), data=_PDF)
    # No DB write and no audit row when the document never landed in storage.
    assert repo.set_calls == []
    assert audit.records == []
