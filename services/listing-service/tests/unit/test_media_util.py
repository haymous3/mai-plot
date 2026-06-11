"""Media validation + key derivation helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.media import InvalidMedia, build_media_key, validate_media

_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01 photo bytes"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16

_LIMITS = {"max_photo_bytes": 5_000_000, "max_video_bytes": 200_000_000}


def test_accepts_jpeg_photo() -> None:
    info = validate_media(_JPEG, declared_type="photo", **_LIMITS)
    assert info.kind == "photo"
    assert info.content_type == "image/jpeg"
    assert info.extension == "jpg"


def test_accepts_png_photo() -> None:
    info = validate_media(_PNG, declared_type="photo", **_LIMITS)
    assert info.content_type == "image/png"
    assert info.extension == "png"


def test_accepts_mp4_video() -> None:
    info = validate_media(_MP4, declared_type="video", **_LIMITS)
    assert info.kind == "video"
    assert info.extension == "mp4"


def test_rejects_unknown_format() -> None:
    with pytest.raises(InvalidMedia) as exc:
        validate_media(b"GIF89a not allowed", declared_type="photo", **_LIMITS)
    assert exc.value.code == "MEDIA_FORMAT_INVALID"


def test_rejects_empty() -> None:
    with pytest.raises(InvalidMedia) as exc:
        validate_media(b"", declared_type="photo", **_LIMITS)
    assert exc.value.code == "MEDIA_FORMAT_INVALID"


def test_rejects_type_mismatch() -> None:
    # bytes are a photo but the client declared a video.
    with pytest.raises(InvalidMedia) as exc:
        validate_media(_JPEG, declared_type="video", **_LIMITS)
    assert exc.value.code == "MEDIA_TYPE_MISMATCH"


def test_rejects_oversize_photo() -> None:
    with pytest.raises(InvalidMedia) as exc:
        validate_media(_JPEG, declared_type="photo", max_photo_bytes=8, max_video_bytes=10)
    assert exc.value.code == "MEDIA_TOO_LARGE"


def test_error_never_contains_bytes() -> None:
    secret = b"\xff\xd8\xff secret-watermark-text"
    try:
        validate_media(secret, declared_type="video", **_LIMITS)
    except InvalidMedia as exc:
        assert "secret" not in str(exc)


def test_media_key_shape() -> None:
    listing_id = uuid4()
    key = build_media_key(listing_id, extension="jpg")
    assert key.startswith(f"listings/{listing_id}/media/")
    assert key.endswith(".jpg")


def test_media_keys_unique() -> None:
    listing_id = uuid4()
    assert build_media_key(listing_id, extension="mp4") != build_media_key(
        listing_id, extension="mp4"
    )
