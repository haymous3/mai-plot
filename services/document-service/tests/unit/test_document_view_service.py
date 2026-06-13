"""DocumentViewService — authorization (IDOR), verified gate, watermark."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.adapters.watermark import FakeWatermarker
from app.repositories.document_repo import ViewDoc
from app.security import CurrentUser
from app.services.document_view import (
    DocumentNotFound,
    DocumentNotViewable,
    DocumentStorageUnavailable,
    DocumentViewService,
)

_KEY = "listings/x/documents/doc.pdf"
_PDF = b"%PDF-1.4 deed"
_SELLER_ID = uuid4()
_LISTING_ID = uuid4()


def _doc(status: str = "verified") -> ViewDoc:
    return ViewDoc(
        s3_key=_KEY, verification_status=status, listing_id=_LISTING_ID, seller_id=_SELLER_ID
    )


class _StubDocRepo:
    def __init__(self, doc: ViewDoc | None) -> None:
        self._doc = doc

    async def get_view(self, document_id: UUID) -> ViewDoc | None:
        return self._doc


class _StubListingRepo:
    def __init__(self, has_offer: bool = False) -> None:
        self._has_offer = has_offer

    async def has_active_offer(self, *, listing_id: UUID, buyer_id: UUID) -> bool:
        return self._has_offer


class _StubUserRepo:
    def __init__(self, name: str | None) -> None:
        self._name = name

    async def get_display_name(self, user_id: UUID) -> str | None:
        return self._name


def _service(
    doc: ViewDoc | None,
    *,
    name: str | None = "Ada Buyer",
    with_bytes: bool = True,
    has_offer: bool = False,
) -> DocumentViewService:
    storage = InMemoryDocumentStorage()
    if with_bytes and doc is not None:
        storage.data[doc.s3_key] = _PDF
    return DocumentViewService(
        documents=_StubDocRepo(doc),  # type: ignore[arg-type]
        listings=_StubListingRepo(has_offer),  # type: ignore[arg-type]
        users=_StubUserRepo(name),  # type: ignore[arg-type]
        storage=storage,
        watermarker=FakeWatermarker(),
    )


def _buyer() -> CurrentUser:
    return CurrentUser(user_id=uuid4(), role="buyer")


@pytest.mark.asyncio
async def test_owner_can_view_watermarked() -> None:
    owner = CurrentUser(user_id=_SELLER_ID, role="seller")
    rendered = await _service(_doc()).render(document_id=uuid4(), viewer=owner)
    assert rendered.content_type == "application/pdf"
    assert b"WMARK[" in rendered.content
    assert b"%PDF-1.4 deed" in rendered.content


@pytest.mark.asyncio
async def test_admin_can_view() -> None:
    admin = CurrentUser(user_id=uuid4(), role="admin")
    rendered = await _service(_doc()).render(document_id=uuid4(), viewer=admin)
    assert b"WMARK[" in rendered.content


@pytest.mark.asyncio
async def test_buyer_with_active_offer_can_view() -> None:
    rendered = await _service(_doc(), has_offer=True).render(document_id=uuid4(), viewer=_buyer())
    assert b"WMARK[Ada Buyer" in rendered.content


@pytest.mark.asyncio
async def test_unauthorized_viewer_gets_404_not_existence_leak() -> None:
    # A buyer with no offer (and not the owner/admin) must NOT learn the
    # document exists -> 404, never the bytes.
    with pytest.raises(DocumentNotFound):
        await _service(_doc(), has_offer=False).render(document_id=uuid4(), viewer=_buyer())


@pytest.mark.asyncio
async def test_unverified_document_is_not_viewable_for_authorized() -> None:
    owner = CurrentUser(user_id=_SELLER_ID, role="seller")
    with pytest.raises(DocumentNotViewable):
        await _service(_doc(status="pending")).render(document_id=uuid4(), viewer=owner)


@pytest.mark.asyncio
async def test_missing_document_raises() -> None:
    with pytest.raises(DocumentNotFound):
        await _service(None).render(document_id=uuid4(), viewer=_buyer())


@pytest.mark.asyncio
async def test_storage_missing_is_unavailable() -> None:
    owner = CurrentUser(user_id=_SELLER_ID, role="seller")
    svc = _service(_doc(), with_bytes=False)
    with pytest.raises(DocumentStorageUnavailable):
        await svc.render(document_id=uuid4(), viewer=owner)


@pytest.mark.asyncio
async def test_overlay_falls_back_to_user_id_without_name() -> None:
    admin = CurrentUser(user_id=uuid4(), role="admin")
    rendered = await _service(_doc(), name=None).render(document_id=uuid4(), viewer=admin)
    assert str(admin.user_id).encode() in rendered.content
