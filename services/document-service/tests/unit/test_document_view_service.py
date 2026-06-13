"""DocumentViewService — verified gate, watermark, name overlay."""

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


class _StubDocRepo:
    def __init__(self, doc: ViewDoc | None) -> None:
        self._doc = doc

    async def get_view(self, document_id: UUID) -> ViewDoc | None:
        return self._doc


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
) -> DocumentViewService:
    storage = InMemoryDocumentStorage()
    if with_bytes and doc is not None:
        storage.data[doc.s3_key] = _PDF
    return DocumentViewService(
        documents=_StubDocRepo(doc),  # type: ignore[arg-type]
        users=_StubUserRepo(name),  # type: ignore[arg-type]
        storage=storage,
        watermarker=FakeWatermarker(),
    )


def _viewer() -> CurrentUser:
    return CurrentUser(user_id=uuid4(), role="buyer")


@pytest.mark.asyncio
async def test_verified_document_is_watermarked_with_buyer_name() -> None:
    svc = _service(ViewDoc(s3_key=_KEY, verification_status="verified"))
    rendered = await svc.render(document_id=uuid4(), viewer=_viewer())
    assert rendered.content_type == "application/pdf"
    assert b"WMARK[Ada Buyer" in rendered.content
    assert b"%PDF-1.4 deed" in rendered.content


@pytest.mark.asyncio
async def test_unverified_document_is_not_viewable() -> None:
    svc = _service(ViewDoc(s3_key=_KEY, verification_status="pending"))
    with pytest.raises(DocumentNotViewable):
        await svc.render(document_id=uuid4(), viewer=_viewer())


@pytest.mark.asyncio
async def test_missing_document_raises() -> None:
    with pytest.raises(DocumentNotFound):
        await _service(None).render(document_id=uuid4(), viewer=_viewer())


@pytest.mark.asyncio
async def test_storage_missing_is_unavailable() -> None:
    svc = _service(ViewDoc(s3_key=_KEY, verification_status="verified"), with_bytes=False)
    with pytest.raises(DocumentStorageUnavailable):
        await svc.render(document_id=uuid4(), viewer=_viewer())


@pytest.mark.asyncio
async def test_overlay_falls_back_to_user_id_without_name() -> None:
    viewer = _viewer()
    svc = _service(ViewDoc(s3_key=_KEY, verification_status="verified"), name=None)
    rendered = await svc.render(document_id=uuid4(), viewer=viewer)
    assert str(viewer.user_id).encode() in rendered.content
