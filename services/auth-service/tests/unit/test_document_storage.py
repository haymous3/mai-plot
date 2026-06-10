"""InMemoryDocumentStorage adapter behaviour."""

from __future__ import annotations

import pytest

from app.adapters.document_storage import (
    DocumentStorageError,
    InMemoryDocumentStorage,
)

_DATA = b"%PDF-1.4 fake document bytes"


@pytest.mark.asyncio
async def test_put_records_object_and_bytes() -> None:
    storage = InMemoryDocumentStorage()
    stored = await storage.put(key="poa/u/1.pdf", data=_DATA, content_type="application/pdf")

    assert stored.key == "poa/u/1.pdf"
    assert stored.content_type == "application/pdf"
    assert stored.size == len(_DATA)
    assert storage.objects["poa/u/1.pdf"] == stored
    assert storage.data["poa/u/1.pdf"] == _DATA


@pytest.mark.asyncio
async def test_put_failure_is_storage_error() -> None:
    storage = InMemoryDocumentStorage(fail_next=True)
    with pytest.raises(DocumentStorageError):
        await storage.put(key="poa/u/1.pdf", data=_DATA, content_type="application/pdf")
    # The failure is one-shot; the next call succeeds.
    stored = await storage.put(key="poa/u/2.pdf", data=_DATA, content_type="application/pdf")
    assert stored.key == "poa/u/2.pdf"


def test_presigned_url_references_key_and_ttl() -> None:
    storage = InMemoryDocumentStorage()
    url = storage.presigned_get_url("poa/u/1.pdf", expires_seconds=900)
    assert "poa/u/1.pdf" in url
    assert "900" in url
