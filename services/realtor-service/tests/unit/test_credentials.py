"""Unit tests for realtor upload validation (SCRUM-71).

⚠️ This file used to test the government-ID helpers ONLY, and SCRUM-219 removed
those (`detect_id_document_type`, `validate_id_size`, `build_id_object_key`)
along with the credentials upload itself — as SCRUM-207 had already removed the
ESVARBON normaliser and its tests. That would have left `credentials.py` with no
unit tests at all, so the cases below now cover what actually survives in the
module: inspection report media and the base-location coordinate check.
"""

from __future__ import annotations

import pytest

from app.services.credentials import (
    InvalidCredential,
    detect_photo_type,
    detect_video_type,
    validate_coordinates,
    validate_photo_size,
    validate_video_size,
)

_JPEG = b"\xff\xd8\xff\xe0 photo"
_PNG = b"\x89PNG\r\n\x1a\n photo"
# ISO-BMFF: the 'ftyp' box sits at bytes 4-8, after the 4-byte box length.
_MP4 = b"\x00\x00\x00\x18ftypmp42 video"
_WEBM = b"\x1a\x45\xdf\xa3 video"


def test_detect_photo_type() -> None:
    assert detect_photo_type(_JPEG) == ("image/jpeg", "jpg")
    assert detect_photo_type(_PNG) == ("image/png", "png")


def test_detect_photo_type_rejects_other() -> None:
    # A PDF is a valid upload elsewhere in the platform but never a photo — the
    # type is decided by the BYTES, not by a filename the client chose.
    with pytest.raises(InvalidCredential) as exc:
        detect_photo_type(b"%PDF-1.4 not a photo")
    assert exc.value.code == "PHOTO_INVALID"


def test_validate_photo_size() -> None:
    validate_photo_size(b"abc", max_bytes=10)
    with pytest.raises(InvalidCredential) as empty:
        validate_photo_size(b"", max_bytes=10)
    assert empty.value.code == "PHOTO_INVALID"
    with pytest.raises(InvalidCredential) as big:
        validate_photo_size(b"abcdefghijk", max_bytes=10)
    assert big.value.code == "PHOTO_TOO_LARGE"


def test_detect_video_type() -> None:
    assert detect_video_type(_MP4) == ("video/mp4", "mp4")
    assert detect_video_type(_WEBM) == ("video/webm", "webm")


def test_detect_video_type_rejects_other() -> None:
    with pytest.raises(InvalidCredential) as exc:
        detect_video_type(_JPEG)
    assert exc.value.code == "VIDEO_INVALID"


def test_detect_video_type_rejects_short_input() -> None:
    # Shorter than the 12 bytes the 'ftyp' probe reads — must raise, not slice
    # past the end and compare an empty string.
    with pytest.raises(InvalidCredential):
        detect_video_type(b"ftyp")


def test_validate_video_size() -> None:
    validate_video_size(b"abc", max_bytes=10)
    with pytest.raises(InvalidCredential) as empty:
        validate_video_size(b"", max_bytes=10)
    assert empty.value.code == "VIDEO_INVALID"
    with pytest.raises(InvalidCredential) as big:
        validate_video_size(b"abcdefghijk", max_bytes=10)
    assert big.value.code == "VIDEO_TOO_LARGE"


def test_validate_coordinates_accepts_lagos() -> None:
    validate_coordinates(6.5244, 3.3792)


@pytest.mark.parametrize(
    ("lat", "lng"),
    [(91.0, 3.4), (-91.0, 3.4), (6.5, 181.0), (6.5, -181.0)],
)
def test_validate_coordinates_rejects_out_of_range(lat: float, lng: float) -> None:
    with pytest.raises(InvalidCredential) as exc:
        validate_coordinates(lat, lng)
    assert exc.value.code == "LOCATION_INVALID"
