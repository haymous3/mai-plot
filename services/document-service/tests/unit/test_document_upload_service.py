"""DocumentUploadService with stub repos + fake storage."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.repositories.listing_repo import ListingOwner
from app.security import CurrentUser
from app.services.document import InvalidDocument
from app.services.document_upload import (
    DocumentStorageUnavailable,
    DocumentUploadService,
    ListingNotFound,
    NotListingOwner,
)

_OWNER_ID = uuid4()
_PDF = b"%PDF-1.7 deed"


class _StubListingRepo:
    def __init__(self, owner: ListingOwner | None) -> None:
        self._owner = owner

    async def get_listing_owner(self, listing_id: UUID) -> ListingOwner | None:
        return self._owner


class _StubDocRepo:
    def __init__(self) -> None:
        self.inserted: dict[str, object] | None = None

    async def insert_document(self, *, listing_id: UUID, document_type: str, s3_key: str) -> UUID:
        self.inserted = {"listing_id": listing_id, "document_type": document_type, "s3_key": s3_key}
        return uuid4()


def _owner_status() -> ListingOwner:
    return ListingOwner(seller_id=_OWNER_ID, status="pending_review")


def _owner() -> CurrentUser:
    return CurrentUser(user_id=_OWNER_ID, role="seller")


def _service(
    listings: _StubListingRepo,
    docs: _StubDocRepo | None = None,
    storage: InMemoryDocumentStorage | None = None,
) -> tuple[DocumentUploadService, _StubDocRepo, InMemoryDocumentStorage]:
    d = docs or _StubDocRepo()
    s = storage or InMemoryDocumentStorage()
    svc = DocumentUploadService(
        listings=listings,  # type: ignore[arg-type]
        documents=d,  # type: ignore[arg-type]
        storage=s,
        max_bytes=10_000,
    )
    return svc, d, s


@pytest.mark.asyncio
async def test_owner_upload_stores_and_inserts() -> None:
    svc, docs, storage = _service(_StubListingRepo(_owner_status()))
    result = await svc.upload(
        listing_id=uuid4(), caller=_owner(), document_type="c_of_o", data=_PDF
    )
    assert result.verification_status == "pending"
    assert docs.inserted is not None
    assert docs.inserted["document_type"] == "c_of_o"
    assert storage.data  # bytes landed in the (fake) private bucket


@pytest.mark.asyncio
async def test_missing_listing_raises() -> None:
    svc, _, _ = _service(_StubListingRepo(None))
    with pytest.raises(ListingNotFound):
        await svc.upload(listing_id=uuid4(), caller=_owner(), document_type="c_of_o", data=_PDF)


@pytest.mark.asyncio
async def test_non_owner_rejected() -> None:
    svc, docs, _ = _service(_StubListingRepo(_owner_status()))
    stranger = CurrentUser(user_id=uuid4(), role="seller")
    with pytest.raises(NotListingOwner):
        await svc.upload(listing_id=uuid4(), caller=stranger, document_type="receipt", data=_PDF)
    assert docs.inserted is None


@pytest.mark.asyncio
async def test_admin_can_upload() -> None:
    svc, docs, _ = _service(_StubListingRepo(_owner_status()))
    admin = CurrentUser(user_id=uuid4(), role="admin")
    await svc.upload(listing_id=uuid4(), caller=admin, document_type="survey_plan", data=_PDF)
    assert docs.inserted is not None


@pytest.mark.asyncio
async def test_invalid_document_raises_before_store() -> None:
    svc, docs, storage = _service(_StubListingRepo(_owner_status()))
    with pytest.raises(InvalidDocument):
        await svc.upload(
            listing_id=uuid4(), caller=_owner(), document_type="c_of_o", data=b"not a pdf"
        )
    assert storage.objects == {}
    assert docs.inserted is None


@pytest.mark.asyncio
async def test_storage_failure_is_unavailable() -> None:
    storage = InMemoryDocumentStorage(fail_next=True)
    svc, docs, _ = _service(_StubListingRepo(_owner_status()), storage=storage)
    with pytest.raises(DocumentStorageUnavailable):
        await svc.upload(listing_id=uuid4(), caller=_owner(), document_type="c_of_o", data=_PDF)
    assert docs.inserted is None
