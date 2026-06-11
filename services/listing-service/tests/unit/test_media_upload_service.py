"""MediaUploadService — ownership, limits, store+insert (redis=None)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.media_storage import InMemoryMediaStorage
from app.repositories.listing_repo import OwnerStatus
from app.security import CurrentUser
from app.services.listing_update import ListingNotFound, NotListingOwner
from app.services.media import InvalidMedia
from app.services.media_upload import (
    MediaLimitExceeded,
    MediaStorageUnavailable,
    MediaUploadService,
)

_OWNER_ID = uuid4()
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF photo"
_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


class _StubRepo:
    def __init__(self, owner: OwnerStatus | None, *, count: int = 0) -> None:
        self._owner = owner
        self._count = count
        self.inserted: dict[str, object] | None = None

    async def get_owner_status(self, listing_id: UUID) -> OwnerStatus | None:
        return self._owner

    async def count_media(self, listing_id: UUID, media_type: str) -> int:
        return self._count

    async def insert_media(self, **kwargs: object) -> UUID:
        self.inserted = kwargs
        return uuid4()


def _owner_status() -> OwnerStatus:
    return OwnerStatus(seller_id=_OWNER_ID, status="active", sale_type="normal")


def _owner() -> CurrentUser:
    return CurrentUser(user_id=_OWNER_ID, role="seller")


def _service(
    repo: _StubRepo,
    storage: InMemoryMediaStorage | None = None,
    *,
    max_photos: int = 15,
    max_videos: int = 1,
    max_photo_bytes: int = 5_000_000,
) -> MediaUploadService:
    return MediaUploadService(
        redis=None,
        listings=repo,  # type: ignore[arg-type]
        storage=storage or InMemoryMediaStorage(),
        max_photo_bytes=max_photo_bytes,
        max_video_bytes=200_000_000,
        max_photos=max_photos,
        max_videos=max_videos,
    )


@pytest.mark.asyncio
async def test_happy_photo_stores_and_inserts() -> None:
    repo, storage = _StubRepo(_owner_status()), InMemoryMediaStorage()
    result = await _service(repo, storage).upload(
        listing_id=uuid4(), caller=_owner(), media_type="photo", data=_JPEG, sort_order=2
    )
    assert result.cdn_url.startswith("https://")
    assert repo.inserted is not None
    assert repo.inserted["media_type"] == "photo"
    assert repo.inserted["sort_order"] == 2
    assert storage.data  # bytes landed in the (fake) bucket


@pytest.mark.asyncio
async def test_missing_listing_raises() -> None:
    with pytest.raises(ListingNotFound):
        await _service(_StubRepo(None)).upload(
            listing_id=uuid4(), caller=_owner(), media_type="photo", data=_JPEG, sort_order=0
        )


@pytest.mark.asyncio
async def test_non_owner_rejected() -> None:
    repo = _StubRepo(_owner_status())
    stranger = CurrentUser(user_id=uuid4(), role="seller")
    with pytest.raises(NotListingOwner):
        await _service(repo).upload(
            listing_id=uuid4(), caller=stranger, media_type="photo", data=_JPEG, sort_order=0
        )
    assert repo.inserted is None


@pytest.mark.asyncio
async def test_admin_can_upload() -> None:
    repo = _StubRepo(_owner_status())
    admin = CurrentUser(user_id=uuid4(), role="admin")
    await _service(repo).upload(
        listing_id=uuid4(), caller=admin, media_type="photo", data=_JPEG, sort_order=0
    )
    assert repo.inserted is not None


@pytest.mark.asyncio
async def test_photo_limit_enforced() -> None:
    repo = _StubRepo(_owner_status(), count=15)
    with pytest.raises(MediaLimitExceeded):
        await _service(repo, max_photos=15).upload(
            listing_id=uuid4(), caller=_owner(), media_type="photo", data=_JPEG, sort_order=0
        )
    assert repo.inserted is None


@pytest.mark.asyncio
async def test_video_limit_enforced() -> None:
    repo = _StubRepo(_owner_status(), count=1)
    with pytest.raises(MediaLimitExceeded):
        await _service(repo, max_videos=1).upload(
            listing_id=uuid4(), caller=_owner(), media_type="video", data=_MP4, sort_order=0
        )


@pytest.mark.asyncio
async def test_invalid_media_raises_before_store() -> None:
    repo, storage = _StubRepo(_owner_status()), InMemoryMediaStorage()
    with pytest.raises(InvalidMedia):
        await _service(repo, storage).upload(
            listing_id=uuid4(), caller=_owner(), media_type="photo", data=b"nope", sort_order=0
        )
    assert storage.objects == {}
    assert repo.inserted is None


@pytest.mark.asyncio
async def test_storage_failure_is_unavailable() -> None:
    repo = _StubRepo(_owner_status())
    storage = InMemoryMediaStorage(fail_next=True)
    with pytest.raises(MediaStorageUnavailable):
        await _service(repo, storage).upload(
            listing_id=uuid4(), caller=_owner(), media_type="photo", data=_JPEG, sort_order=0
        )
    assert repo.inserted is None
