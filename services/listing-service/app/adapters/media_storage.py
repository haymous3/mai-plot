"""Media storage adapter — listing photos/videos.

Listing media is PUBLIC content, but the only bucket we have (Railway's
`maihomme-files`) is PRIVATE. So since SCRUM-252 nothing stores a bucket URL:
listing_media.cdn_url holds a STABLE listing-service link
(`{media_public_base_url}/listings/media/{media_id}`), and that endpoint
302-redirects to `url_for(key)` — a short-lived pre-signed GET, or the plain
CDN URL once a public CDN domain is configured. The bytes go browser <-> bucket
directly; the service only mints the redirect.

  * MediaStorage — Protocol every call site depends on.
  * S3MediaStorage — real adapter, boto3 put + presign against the bucket.
  * InMemoryMediaStorage — in-process fake for local + CI (no network).

The media BYTES pass through on upload but are never logged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredMedia:
    key: str
    size: int


class MediaStorageError(RuntimeError):
    """Raised when the storage backend itself fails (network/5xx/credentials)."""


class MediaStorage(Protocol):
    async def put(
        self, *, key: str, data: bytes, content_type: str
    ) -> StoredMedia:  # pragma: no cover - protocol
        ...

    def url_for(self, key: str) -> str:  # pragma: no cover - protocol
        """Where a browser can fetch the object right now. Local computation
        (no network), so it is safe on the request path."""
        ...


def _cdn_url(domain: str, key: str) -> str:
    return f"https://{domain}/{key}"


@dataclass
class InMemoryMediaStorage:
    """Test double. Holds objects in a dict keyed by S3 key so a test can
    assert what was stored without a network round trip."""

    cdn_domain: str = ""
    objects: dict[str, StoredMedia] = field(default_factory=dict)
    data: dict[str, bytes] = field(default_factory=dict)
    fail_next: bool = False

    async def put(self, *, key: str, data: bytes, content_type: str) -> StoredMedia:
        if self.fail_next:
            self.fail_next = False
            raise MediaStorageError("simulated storage failure")
        stored = StoredMedia(key=key, size=len(data))
        self.objects[key] = stored
        self.data[key] = data
        return stored

    def url_for(self, key: str) -> str:
        return _cdn_url(self.cdn_domain or "cdn.maiplot.local", key)


class S3MediaStorage:
    """Puts objects into the media bucket. With no CDN domain (the Railway
    private bucket) `url_for` pre-signs a GET; with one, it returns the public
    CDN URL. boto3 is synchronous, so the upload runs in a worker thread;
    presigning is local HMAC work and runs inline."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        cdn_domain: str,
        endpoint_url: str | None = None,
        presign_ttl_seconds: int = 3600,
    ) -> None:
        import boto3

        self._bucket = bucket
        self._cdn_domain = cdn_domain
        self._presign_ttl_seconds = presign_ttl_seconds
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,
        )

    async def put(self, *, key: str, data: bytes, content_type: str) -> StoredMedia:
        started = time.perf_counter()
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:  # boto3 raises ClientError/BotoCoreError
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "media.storage.put_failed",
                extra={"key": key, "size": len(data), "duration_ms": duration_ms},
            )
            raise MediaStorageError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "media.storage.put_ok",
            extra={"key": key, "size": len(data), "duration_ms": duration_ms},
        )
        return StoredMedia(key=key, size=len(data))

    def url_for(self, key: str) -> str:
        if self._cdn_domain:
            return _cdn_url(self._cdn_domain, key)
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._presign_ttl_seconds,
        )
        return url


def build_media_storage(
    *,
    use_fake: bool,
    bucket: str,
    region: str,
    cdn_domain: str,
    endpoint_url: str,
    presign_ttl_seconds: int = 3600,
) -> MediaStorage:
    """Factory — in-memory fake for local/CI, real S3 client in production."""
    if use_fake:
        return InMemoryMediaStorage(cdn_domain=cdn_domain)
    return S3MediaStorage(
        bucket=bucket,
        region=region,
        cdn_domain=cdn_domain,
        endpoint_url=endpoint_url,
        presign_ttl_seconds=presign_ttl_seconds,
    )
