"""POST /listings/{id}/media integration tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01 photo bytes here"
_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32


def _photo(name: str = "p.jpg") -> dict[str, Any]:
    return {"file": (name, _JPEG, "image/jpeg")}


@pytest.mark.asyncio
async def test_owner_uploads_photo(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    response = await http_client.post(
        f"/listings/{listing_id}/media",
        files=_photo(),
        data={"media_type": "photo", "sort_order": "1"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # SCRUM-252: a stable link to the redirect endpoint, not a bucket URL.
    assert body["cdn_url"] == f"http://localhost:8000/listings/media/{body['media_id']}"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT media_type, cdn_url, sort_order, size_bytes "
                "FROM listing_media WHERE listing_id = :id"
            ),
            {"id": listing_id},
        ).first()
        assert row is not None
        assert row.media_type == "photo"
        assert row.cdn_url == body["cdn_url"]
        assert row.sort_order == 1
        assert row.size_bytes == len(_JPEG)

    # The new media shows up on the detail endpoint...
    detail = await http_client.get(f"/listings/{listing_id}")
    assert detail.status_code == 200
    assert [m["url"] for m in detail.json()["media"]] == [body["cdn_url"]]

    # ...and following that URL redirects to where the bytes actually are.
    redirect = await http_client.get(f"/listings/media/{body['media_id']}")
    assert redirect.status_code == 302
    key = next(iter(media_storage_fake.data))
    assert redirect.headers["location"] == f"https://cdn.maiplot.test/{key}"
    assert redirect.headers["cache-control"] == "public, max-age=3300"


@pytest.mark.asyncio
async def test_non_owner_cannot_upload(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    owner = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=owner)
    stranger = seed_seller(phone="08087654321")
    token = mint_access_token(stranger, "seller")

    response = await http_client.post(
        f"/listings/{listing_id}/media",
        files=_photo(),
        data={"media_type": "photo"},
        headers=auth_header(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "NOT_LISTING_OWNER")


@pytest.mark.asyncio
async def test_type_mismatch_is_422(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    # JPEG bytes declared as a video.
    response = await http_client.post(
        f"/listings/{listing_id}/media",
        files={"file": ("x.mp4", _JPEG, "video/mp4")},
        data={"media_type": "video"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "MEDIA_TYPE_MISMATCH")


@pytest.mark.asyncio
async def test_unknown_format_is_422(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    response = await http_client.post(
        f"/listings/{listing_id}/media",
        files={"file": ("x.gif", b"GIF89a nope", "image/gif")},
        data={"media_type": "photo"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "MEDIA_FORMAT_INVALID")


@pytest.mark.asyncio
async def test_second_video_exceeds_limit(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")
    video = {"file": ("v.mp4", _MP4, "video/mp4")}

    first = await http_client.post(
        f"/listings/{listing_id}/media",
        files=video,
        data={"media_type": "video"},
        headers=auth_header(token),
    )
    assert first.status_code == 201, first.text

    second = await http_client.post(
        f"/listings/{listing_id}/media",
        files={"file": ("v2.mp4", _MP4, "video/mp4")},
        data={"media_type": "video"},
        headers=auth_header(token),
    )
    assert second.status_code == 422
    assert_error_envelope(second.json(), "MEDIA_LIMIT_EXCEEDED")


@pytest.mark.asyncio
async def test_upload_unknown_listing_is_404(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    token = mint_access_token(seller, "seller")
    response = await http_client.post(
        f"/listings/{uuid4()}/media",
        files=_photo(),
        data={"media_type": "photo"},
        headers=auth_header(token),
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "LISTING_NOT_FOUND")


@pytest.mark.asyncio
async def test_media_upload_requires_auth(
    clean_listing_tables: None,
    disable_cache: None,
    media_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    response = await http_client.post(
        f"/listings/{listing_id}/media",
        files=_photo(),
        data={"media_type": "photo"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")


@pytest.mark.asyncio
async def test_unknown_media_id_is_404(
    clean_listing_tables: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.get(f"/listings/media/{uuid4()}")
    assert response.status_code == 404
    assert_error_envelope(response.json(), "MEDIA_NOT_FOUND")


@pytest.mark.asyncio
async def test_media_of_a_deleted_listing_is_404(
    clean_listing_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_media: Callable[..., None],
) -> None:
    listing_id = seed_listing(seller_id=seed_seller(phone="08012345678"))
    seed_media(listing_id=listing_id)
    with db_engine.begin() as conn:
        media_id = conn.execute(
            text("SELECT id FROM listing_media WHERE listing_id = :id"), {"id": listing_id}
        ).scalar_one()
        conn.execute(
            text("UPDATE property_listings SET deleted_at = NOW() WHERE id = :id"),
            {"id": listing_id},
        )

    response = await http_client.get(f"/listings/media/{media_id}")
    assert response.status_code == 404
