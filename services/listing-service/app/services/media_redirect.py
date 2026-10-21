"""Resolve a listing media id to a fetchable URL (GET /listings/media/{id}).

SCRUM-252. listing_media.cdn_url stores a stable link to this endpoint instead
of a bucket URL, because the bucket is private and a pre-signed URL expires —
and other services read cdn_url straight from the shared DB. This turns the
stable link into a fresh pre-signed GET (or the public CDN URL, when one is
configured) for the route to 302 to.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.media_storage import MediaStorage
from app.repositories.listing_repo import ListingRepository


class MediaNotFound(Exception):
    pass


@dataclass(frozen=True)
class MediaLocation:
    url: str
    # How long a browser may reuse the redirect. Always shorter than the
    # pre-signed URL's own lifetime, so a cached redirect never points at an
    # expired signature.
    max_age_seconds: int


class MediaRedirectService:
    def __init__(
        self, *, listings: ListingRepository, storage: MediaStorage, presign_ttl_seconds: int
    ) -> None:
        self._listings = listings
        self._storage = storage
        self._max_age = max(0, presign_ttl_seconds - 300)

    async def locate(self, media_id: UUID) -> MediaLocation:
        key = await self._listings.get_media_key(media_id)
        if key is None:
            raise MediaNotFound()
        return MediaLocation(url=self._storage.url_for(key), max_age_seconds=self._max_age)
