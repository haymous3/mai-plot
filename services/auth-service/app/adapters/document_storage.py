"""Document storage adapter — private S3 bucket for PoA documents.

Mirrors the Termii/BVN/NIN adapter shape:
  * DocumentStorage — Protocol every call site depends on.
  * S3DocumentStorage — real adapter, puts to a PRIVATE bucket and mints
    short-TTL pre-signed GET URLs (CLAUDE.md: documents are never public).
  * InMemoryDocumentStorage — in-process fake for local + CI; keeps the
    bytes in a dict so tests never touch the network.

The document BYTES pass through here on upload but are NEVER logged. Log
lines key off the object key, size, and content type only.
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
    """What a successful put recorded — the key callers persist, plus the
    metadata used for the audit log. Never carries the bytes."""

    key: str
    content_type: str
    size: int


class DocumentStorageError(RuntimeError):
    """Raised when the storage backend itself fails (network/5xx/credentials)
    — distinct from a validation failure, which never reaches the adapter."""


class DocumentObjectMissing(DocumentStorageError):
    """The requested object key does not exist in the bucket."""


class DocumentStorage(Protocol):
    async def put(
        self, *, key: str, data: bytes, content_type: str
    ) -> StoredObject:  # pragma: no cover - protocol
        ...

    async def get(self, key: str) -> bytes:  # pragma: no cover - protocol
        ...

    def presigned_get_url(
        self, key: str, *, expires_seconds: int
    ) -> str:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryDocumentStorage:
    """Test double. Holds objects in a dict keyed by S3 key. `objects` lets a
    test assert what was stored without ever exposing it over a network."""

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

    async def get(self, key: str) -> bytes:
        if key not in self.data:
            raise DocumentObjectMissing(key)
        return self.data[key]

    def presigned_get_url(self, key: str, *, expires_seconds: int) -> str:
        # Deterministic fake URL — no real signing, just enough for callers
        # and tests to assert a URL was produced for the right key.
        return f"memory://documents/{key}?expires={expires_seconds}"


class S3DocumentStorage:
    """Puts objects into a PRIVATE S3 bucket (no ACL, private by default) and
    serves them only via pre-signed GET URLs. boto3 is synchronous, so the
    blocking calls run in a worker thread to keep the event loop free."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
    ) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,
        )

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
            # No bytes in the log — only the key, size, and error class.
            logger.error(
                "poa.storage.put_failed",
                extra={"key": key, "size": len(data), "duration_ms": duration_ms},
            )
            raise DocumentStorageError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "poa.storage.put_ok",
            extra={"key": key, "size": len(data), "duration_ms": duration_ms},
        )
        return StoredObject(key=key, content_type=content_type, size=len(data))

    async def get(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
            body: bytes = await asyncio.to_thread(response["Body"].read)
        except self._client.exceptions.NoSuchKey as exc:
            raise DocumentObjectMissing(key) from exc
        except Exception as exc:  # boto3 ClientError/BotoCoreError
            raise DocumentStorageError(str(exc)) from exc
        return body

    def presigned_get_url(self, key: str, *, expires_seconds: int) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return url


def build_document_storage(
    *,
    use_fake: bool,
    bucket: str,
    region: str,
    endpoint_url: str,
) -> DocumentStorage:
    """Factory — in-memory fake for local/CI, real S3 client in production."""
    if use_fake:
        return InMemoryDocumentStorage()
    return S3DocumentStorage(bucket=bucket, region=region, endpoint_url=endpoint_url)
