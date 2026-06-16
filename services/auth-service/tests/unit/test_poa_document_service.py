"""PoaDocumentService — serve bytes, infer content-type, audit, not-found."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.security import CurrentUser
from app.services.poa_document import PoaDocumentNotFound, PoaDocumentService

_VIEWER = CurrentUser(user_id=uuid4(), role="legal_team")
_PDF = b"%PDF-1.4 power of attorney"


class _StubUserRepo:
    def __init__(self, key: str | None) -> None:
        self._key = key

    async def get_poa_document_key(self, user_id: UUID) -> str | None:
        return self._key


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service(
    key: str | None, storage: InMemoryDocumentStorage
) -> tuple[PoaDocumentService, _StubAudit]:
    audit = _StubAudit()
    svc = PoaDocumentService(
        users=_StubUserRepo(key),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        storage=storage,
    )
    return svc, audit


@pytest.mark.asyncio
async def test_serves_bytes_with_pdf_content_type_and_audits() -> None:
    key = "poa/abc/doc.pdf"
    storage = InMemoryDocumentStorage()
    await storage.put(key=key, data=_PDF, content_type="application/pdf")
    svc, audit = _service(key, storage)

    doc = await svc.get_document(user_id=uuid4(), viewer=_VIEWER)

    assert doc.content == _PDF
    assert doc.content_type == "application/pdf"
    assert audit.actions == ["poa.document_viewed"]


@pytest.mark.asyncio
async def test_infers_jpeg_content_type() -> None:
    key = "poa/abc/scan.jpg"
    storage = InMemoryDocumentStorage()
    await storage.put(key=key, data=b"\xff\xd8\xff scan", content_type="image/jpeg")
    svc, _ = _service(key, storage)

    doc = await svc.get_document(user_id=uuid4(), viewer=_VIEWER)
    assert doc.content_type == "image/jpeg"


@pytest.mark.asyncio
async def test_no_document_on_file_raises_not_found() -> None:
    svc, audit = _service(None, InMemoryDocumentStorage())
    with pytest.raises(PoaDocumentNotFound):
        await svc.get_document(user_id=uuid4(), viewer=_VIEWER)
    assert audit.actions == []  # nothing viewed, nothing audited


@pytest.mark.asyncio
async def test_missing_object_in_bucket_raises_not_found() -> None:
    # Key recorded on the user, but the object is absent from the bucket.
    svc, _ = _service("poa/abc/gone.pdf", InMemoryDocumentStorage())
    with pytest.raises(PoaDocumentNotFound):
        await svc.get_document(user_id=uuid4(), viewer=_VIEWER)
