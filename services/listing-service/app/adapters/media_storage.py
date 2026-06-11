"""Media storage adapter — PUBLIC listing photos/videos.

Mirrors the SCRUM-48 document-storage shape, but media is public: objects go
to the media bucket and are served via CloudFront, so `put` returns a
precomputed `cdn_url` instead of minting a pre-signed URL. (PoA/legal docs
use the private + pre-signed pattern; listing media does not.)

  * MediaStorage — Protocol every call site depends on.
  * S3MediaStorage — real adapter, boto3 put to the media bucket.
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
    cdn_url: str
    size: int


class MediaStorageError(RuntimeError):
    """Raised when the storage backend itself fails (network/5xx/credentials)."""


class MediaStorage(Protocol):
    async def put(
        self, *, key: str, data: bytes, content_type: str
    ) -> StoredMedia:  # pragma: no cover - protocol
        ...


def _cdn_url(domain: str, key: str) -> str:
    return f"https://{domain}/{key}"


@dataclass
class InMemoryMediaStorage:
    """Test double. Holds objects in a dict keyed by S3 key so a test can
    assert what was stored without a network round trip."""

    cdn_domain: str = "cdn.maiplot.local"
    objects: dict[str, StoredMedia] = field(default_factory=dict)
    data: dict[str, bytes] = field(default_factory=dict)
    fail_next: bool = False

    async def put(self, *, key: str, data: bytes, content_type: str) -> StoredMedia:
        if self.fail_next:
            self.fail_next = False
            raise MediaStorageError("simulated storage failure")
        stored = StoredMedia(key=key, cdn_url=_cdn_url(self.cdn_domain, key), size=len(data))
        self.objects[key] = stored
        self.data[key] = data
        return stored


class S3MediaStorage:
    """Puts objects into the media bucket and returns their CloudFront URL.
    boto3 is synchronous, so the blocking call runs in a worker thread."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        cdn_domain: str,
        endpoint_url: str | None = None,
    ) -> None:
        import boto3

        self._bucket = bucket
        self._cdn_domain = cdn_domain
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
        return StoredMedia(key=key, cdn_url=_cdn_url(self._cdn_domain, key), size=len(data))


def build_media_storage(
    *,
    use_fake: bool,
    bucket: str,
    region: str,
    cdn_domain: str,
    endpoint_url: str,
) -> MediaStorage:
    """Factory — in-memory fake for local/CI, real S3 client in production."""
    if use_fake:
        return InMemoryMediaStorage(cdn_domain=cdn_domain)
    return S3MediaStorage(
        bucket=bucket, region=region, cdn_domain=cdn_domain, endpoint_url=endpoint_url
    )
