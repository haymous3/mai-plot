"""Media upload orchestration (POST /listings/{id}/media).

Only the owning seller (or an admin) may add media. The file is validated
server-side by its magic bytes (must match the declared photo/video type and
size limits), the per-type cap is enforced (max photos / max videos), the
object is stored in the PUBLIC media bucket, and a listing_media row is
written with the precomputed CloudFront URL. The cached listing detail
(`listing:{id}`) is invalidated so the new media shows up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.adapters.media_storage import MediaStorage, MediaStorageError
from app.repositories.listing_repo import ListingRepository
from app.security import CurrentUser
from app.services.listing_update import ListingNotFound, NotListingOwner
from app.services.media import build_media_key, validate_media

logger = logging.getLogger(__name__)


class MediaUploadError(RuntimeError):
    pass


class MediaLimitExceeded(MediaUploadError):
    """The listing already has the maximum number of this media type."""


class MediaStorageUnavailable(MediaUploadError):
    """The storage backend failed — a retryable condition."""


@dataclass(frozen=True)
class MediaUploadResult:
    media_id: UUID
    cdn_url: str


class MediaUploadService:
    def __init__(
        self,
        *,
        redis: Redis | None,
        listings: ListingRepository,
        storage: MediaStorage,
        max_photo_bytes: int,
        max_video_bytes: int,
        max_photos: int,
        max_videos: int,
    ) -> None:
        self._redis = redis
        self._listings = listings
        self._storage = storage
        self._max_photo_bytes = max_photo_bytes
        self._max_video_bytes = max_video_bytes
        self._max_photos = max_photos
        self._max_videos = max_videos

    async def upload(
        self,
        *,
        listing_id: UUID,
        caller: CurrentUser,
        media_type: str,
        data: bytes,
        sort_order: int,
    ) -> MediaUploadResult:
        owner = await self._listings.get_owner_status(listing_id)
        if owner is None:
            raise ListingNotFound()
        if caller.role != "admin" and owner.seller_id != caller.user_id:
            raise NotListingOwner()

        # Validate the bytes against the declared type + size (422 on failure).
        info = validate_media(
            data,
            declared_type=media_type,
            max_photo_bytes=self._max_photo_bytes,
            max_video_bytes=self._max_video_bytes,
        )

        cap = self._max_photos if media_type == "photo" else self._max_videos
        if await self._listings.count_media(listing_id, media_type) >= cap:
            raise MediaLimitExceeded()

        key = build_media_key(listing_id, extension=info.extension)
        try:
            stored = await self._storage.put(key=key, data=data, content_type=info.content_type)
        except MediaStorageError as exc:
            logger.error("media.upload.storage_unavailable", extra={"listing_id": str(listing_id)})
            raise MediaStorageUnavailable() from exc

        media_id = await self._listings.insert_media(
            listing_id=listing_id,
            media_type=media_type,
            s3_key=key,
            cdn_url=stored.cdn_url,
            sort_order=sort_order,
            size_bytes=stored.size,
        )
        await self._invalidate(listing_id)
        return MediaUploadResult(media_id=media_id, cdn_url=stored.cdn_url)

    async def _invalidate(self, listing_id: UUID) -> None:
        """Best-effort detail-cache bust so the new media appears; a Redis
        failure here must not fail the already-stored upload."""
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"listing:{listing_id}")
        except RedisError as exc:
            logger.warning(
                "redis.invalidate.failed", extra={"id": str(listing_id), "error": str(exc)}
            )
