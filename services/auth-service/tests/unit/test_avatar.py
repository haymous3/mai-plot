"""Unit tests for profile-photo validation and key derivation (SCRUM-188).

The security property under test is that the ACCEPTED SET IS DECIDED BY THE
BYTES. A client can claim any filename or Content-Type it likes; only the magic
number is trusted.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.avatar import (
    InvalidAvatar,
    build_object_key,
    detect_image_type,
    validate_size,
)

# Minimal byte prefixes for each format. Only the leading magic matters here.
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"\x00" * 16


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_JPEG, ("image/jpeg", "jpg")),
        (_PNG, ("image/png", "png")),
        (_WEBP, ("image/webp", "webp")),
    ],
)
def test_detects_each_accepted_format(data: bytes, expected: tuple[str, str]) -> None:
    assert detect_image_type(data) == expected


def test_rejects_pdf_even_though_the_poa_path_accepts_it() -> None:
    """An avatar is rendered in an <img>; PDF is valid for a PoA and not here."""
    with pytest.raises(InvalidAvatar) as exc:
        detect_image_type(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3")
    assert exc.value.code == "AVATAR_INVALID"


def test_rejects_svg() -> None:
    """SVG is script-bearing — an embedded <script>/onload is stored XSS if the
    file is ever served same-origin. Raster only, by design."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(InvalidAvatar) as exc:
        detect_image_type(svg)
    assert exc.value.code == "AVATAR_INVALID"


def test_riff_container_that_is_not_webp_is_rejected() -> None:
    """A WAV is also RIFF. The WEBP tag at offset 8 is what distinguishes it, so
    checking only the leading four bytes would let audio through."""
    wav = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE" + b"\x00" * 16
    with pytest.raises(InvalidAvatar):
        detect_image_type(wav)


def test_a_renamed_executable_is_rejected() -> None:
    """The whole point of sniffing: `payload.exe` renamed to `me.png` with a
    truthful-looking Content-Type still fails, because the bytes are wrong."""
    with pytest.raises(InvalidAvatar):
        detect_image_type(b"MZ\x90\x00\x03" + b"\x00" * 32)


def test_empty_file_rejected() -> None:
    with pytest.raises(InvalidAvatar) as exc:
        validate_size(b"", max_bytes=1024)
    assert exc.value.code == "AVATAR_INVALID"


def test_oversized_file_rejected_with_its_own_code() -> None:
    """Distinct from AVATAR_INVALID so the UI can say "too big" rather than
    "wrong format", which are different user problems."""
    with pytest.raises(InvalidAvatar) as exc:
        validate_size(b"x" * 11, max_bytes=10)
    assert exc.value.code == "AVATAR_TOO_LARGE"


def test_size_at_the_limit_is_accepted() -> None:
    validate_size(b"x" * 10, max_bytes=10)


def test_error_never_echoes_the_bytes() -> None:
    """Validation messages must not carry image content back to the caller."""
    secret = b"\x00SUPER_SECRET_MARKER"
    with pytest.raises(InvalidAvatar) as exc:
        detect_image_type(secret)
    assert "SUPER_SECRET_MARKER" not in str(exc.value)


def test_key_is_scoped_to_the_user_and_unguessable() -> None:
    user_id = uuid4()
    key = build_object_key(user_id, extension="png")
    assert key.startswith(f"avatar/{user_id}/")
    assert key.endswith(".png")


def test_two_uploads_never_share_a_key() -> None:
    """A replacement must not overwrite the old object in place, or a pre-signed
    URL already in flight would silently start resolving to a different image."""
    user_id = uuid4()
    assert build_object_key(user_id, extension="jpg") != build_object_key(user_id, extension="jpg")
