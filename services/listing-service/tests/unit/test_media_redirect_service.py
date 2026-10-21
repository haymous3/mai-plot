"""MediaRedirectService — stable media link -> fetchable URL (SCRUM-252)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.media_storage import InMemoryMediaStorage
from app.services.media_redirect import MediaNotFound, MediaRedirectService


class _StubRepo:
    def __init__(self, keys: dict[UUID, str]) -> None:
        self._keys = keys

    async def get_media_key(self, media_id: UUID) -> str | None:
        return self._keys.get(media_id)


def _service(keys: dict[UUID, str], *, ttl: int = 3600) -> MediaRedirectService:
    return MediaRedirectService(
        listings=_StubRepo(keys),  # type: ignore[arg-type]
        storage=InMemoryMediaStorage(cdn_domain="cdn.test"),
        presign_ttl_seconds=ttl,
    )


@pytest.mark.asyncio
async def test_locates_the_object_behind_a_media_id() -> None:
    media_id = uuid4()
    location = await _service({media_id: "listings/a/media/1.jpg"}).locate(media_id)
    assert location.url == "https://cdn.test/listings/a/media/1.jpg"


@pytest.mark.asyncio
async def test_browser_cache_lifetime_stays_inside_the_signature_lifetime() -> None:
    """A cached 302 must never outlive the pre-signed URL it points at."""
    media_id = uuid4()
    location = await _service({media_id: "k"}, ttl=3600).locate(media_id)
    assert location.max_age_seconds == 3300
    short = await _service({media_id: "k"}, ttl=120).locate(media_id)
    assert short.max_age_seconds == 0


@pytest.mark.asyncio
async def test_unknown_media_raises() -> None:
    with pytest.raises(MediaNotFound):
        await _service({}).locate(uuid4())
