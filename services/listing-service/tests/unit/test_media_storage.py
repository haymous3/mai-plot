"""Media storage adapters — InMemoryMediaStorage, S3MediaStorage.url_for."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import pytest

from app.adapters.media_storage import InMemoryMediaStorage, MediaStorageError, S3MediaStorage

_DATA = b"\xff\xd8\xff photo bytes"


@pytest.mark.asyncio
async def test_put_records_object_and_url_for_resolves_it() -> None:
    storage = InMemoryMediaStorage(cdn_domain="cdn.example.com")
    stored = await storage.put(key="listings/x/media/1.jpg", data=_DATA, content_type="image/jpeg")

    assert stored.key == "listings/x/media/1.jpg"
    assert storage.url_for(stored.key) == "https://cdn.example.com/listings/x/media/1.jpg"
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


# --- S3MediaStorage.url_for (SCRUM-252) -------------------------------------


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Callable[..., S3MediaStorage]:
    """Build an S3MediaStorage with fake static credentials: presigning is
    local HMAC work, so nothing touches the network."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")

    def _build(*, cdn_domain: str, presign_ttl_seconds: int = 3600) -> S3MediaStorage:
        return S3MediaStorage(
            bucket="maihomme-files",
            region="auto",
            endpoint_url="https://storage.example.test",
            cdn_domain=cdn_domain,
            presign_ttl_seconds=presign_ttl_seconds,
        )

    return _build


def test_private_bucket_url_is_presigned_with_the_configured_ttl(
    s3: Callable[..., S3MediaStorage],
) -> None:
    url = s3(cdn_domain="", presign_ttl_seconds=1800).url_for("listings/x/media/1.jpg")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://storage.example.test/maihomme-files/listings/x/media/1.jpg"
    )
    assert query["X-Amz-Expires"] == ["1800"]
    assert "X-Amz-Signature" in query


def test_public_cdn_domain_skips_presigning(s3: Callable[..., S3MediaStorage]) -> None:
    url = s3(cdn_domain="cdn.maihomme.com").url_for("listings/x/media/1.jpg")
    assert url == "https://cdn.maihomme.com/listings/x/media/1.jpg"
