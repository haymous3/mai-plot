"""InMemoryMediaStorage adapter behaviour."""

from __future__ import annotations

import pytest

from app.adapters.media_storage import InMemoryMediaStorage, MediaStorageError

_DATA = b"\xff\xd8\xff photo bytes"


@pytest.mark.asyncio
async def test_put_records_object_and_cdn_url() -> None:
    storage = InMemoryMediaStorage(cdn_domain="cdn.example.com")
    stored = await storage.put(key="listings/x/media/1.jpg", data=_DATA, content_type="image/jpeg")

    assert stored.key == "listings/x/media/1.jpg"
    assert stored.cdn_url == "https://cdn.example.com/listings/x/media/1.jpg"
    assert stored.size == len(_DATA)
    assert storage.data["listings/x/media/1.jpg"] == _DATA


@pytest.mark.asyncio
async def test_put_failure_is_storage_error() -> None:
    storage = InMemoryMediaStorage(fail_next=True)
    with pytest.raises(MediaStorageError):
        await storage.put(key="k", data=_DATA, content_type="image/jpeg")
    # one-shot: next call succeeds
    stored = await storage.put(key="k2", data=_DATA, content_type="image/jpeg")
    assert stored.key == "k2"
