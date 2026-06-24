"""Document storage adapter — private S3 bucket for realtor ID documents.

Mirrors auth-service's PoA storage:
  * DocumentStorage — Protocol every call site depends on.
  * S3DocumentStorage — real adapter, puts to a PRIVATE bucket and mints
    short-TTL pre-signed GET URLs (CLAUDE.md: documents are never public).
  * InMemoryDocumentStorage — in-process fake for local + CI.

The document BYTES pass through here on upload but are NEVER logged. Log lines
key off the object key, size, and content type only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredObject:
    key: str
    content_type: str
    size: int


class DocumentStorageError(RuntimeError):
    """The storage backend itself failed (network/5xx/credentials)."""


class DocumentObjectMissing(DocumentStorageError):
    """The requested object key does not exist in the bucket."""


class DocumentStorage(Protocol):
    async def put(
        self, *, key: str, data: bytes, content_type: str
    ) -> StoredObject:  # pragma: no cover - protocol
        ...

    def presigned_get_url(
        self, key: str, *, expires_seconds: int
    ) -> str:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryDocumentStorage:
    """Test double — holds objects in a dict keyed by S3 key."""

    objects: dict[str, StoredObject] = field(default_factory=dict)
    data: dict[str, bytes] = field(default_factory=dict)
    fail_next: bool = False

    async def put(self, *, key: str, data: bytes, content_type: str) -> StoredObject:
        if self.fail_next:
            self.fail_next = False
            raise DocumentStorageError("simulated storage failure")
        stored = StoredObject(key=key, content_type=content_type, size=len(data))
        self.objects[key] = stored
        self.data[key] = data
        return stored

    def presigned_get_url(self, key: str, *, expires_seconds: int) -> str:
        return f"memory://documents/{key}?expires={expires_seconds}"


class S3DocumentStorage:
    """Puts objects into a PRIVATE S3 bucket and serves them only via pre-signed
    GET URLs. boto3 is synchronous, so the blocking calls run in a thread."""

    def __init__(self, *, bucket: str, region: str, endpoint_url: str | None = None) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url or None)

    async def put(self, *, key: str, data: bytes, content_type: str) -> StoredObject:
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
                "realtor.id.storage.put_failed",
                extra={"key": key, "size": len(data), "duration_ms": duration_ms},
            )
            raise DocumentStorageError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "realtor.id.storage.put_ok",
            extra={"key": key, "size": len(data), "duration_ms": duration_ms},
        )
        return StoredObject(key=key, content_type=content_type, size=len(data))

    def presigned_get_url(self, key: str, *, expires_seconds: int) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return url


def build_document_storage(
    *, use_fake: bool, bucket: str, region: str, endpoint_url: str
) -> DocumentStorage:
    """Factory — in-memory fake for local/CI, real S3 client in production."""
    if use_fake:
        return InMemoryDocumentStorage()
    return S3DocumentStorage(bucket=bucket, region=region, endpoint_url=endpoint_url)
