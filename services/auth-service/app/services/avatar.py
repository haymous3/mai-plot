"""Profile-photo validation + key derivation (SCRUM-188).

Deliberately mirrors `poa.py`: the content type is decided by SNIFFING THE
BYTES, never by trusting the client's filename or Content-Type header. A
browser will happily label anything `image/png`, and the private bucket must
not become a way to park arbitrary payloads.

The accepted set is narrower than PoA's and different in kind — an avatar is
displayed in an `<img>`, so it must be a real raster image. PDF is not
accepted here even though the PoA path takes it.

⚠️ SVG is deliberately NOT accepted. It is a script-bearing document: an
`<svg>` with an embedded `<script>` or `onload` executes if it is ever served
same-origin, which turns a profile photo into stored XSS. Raster only.
"""

from __future__ import annotations

from uuid import UUID, uuid4

# Magic numbers for the accepted raster formats.
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# WebP is a RIFF container: "RIFF" <4-byte size> "WEBP", so the tag sits at
# offset 8 and the size bytes in between are not fixed.
_RIFF_MAGIC = b"RIFF"
_WEBP_TAG = b"WEBP"


class InvalidAvatar(ValueError):
    """The uploaded file is not an accepted image or violates a size bound.

    Carries a machine code (never the bytes) so the route can map it to a
    specific 422 without echoing image content back to the caller.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_image_type(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the file's magic bytes.

    Raises InvalidAvatar(AVATAR_INVALID) for anything that is not a JPEG, PNG
    or WebP. The bytes are inspected, never logged or echoed.
    """
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg", "jpg"
    if data.startswith(_PNG_MAGIC):
        return "image/png", "png"
    if data.startswith(_RIFF_MAGIC) and data[8:12] == _WEBP_TAG:
        return "image/webp", "webp"
    raise InvalidAvatar("AVATAR_INVALID", "Profile photo must be a JPEG, PNG or WebP image.")


def validate_size(data: bytes, *, max_bytes: int) -> None:
    """Reject an empty file or one larger than the configured ceiling."""
    if len(data) == 0:
        raise InvalidAvatar("AVATAR_INVALID", "Profile photo is empty.")
    if len(data) > max_bytes:
        raise InvalidAvatar(
            "AVATAR_TOO_LARGE",
            f"Profile photo exceeds the {max_bytes} byte limit.",
        )


def build_object_key(user_id: UUID, *, extension: str) -> str:
    """Private-bucket key: avatar/{user_id}/{uuid}.{ext}.

    The random uuid makes the key unguessable and means a replacement upload
    never reuses the old key — so a pre-signed URL already in flight keeps
    resolving to the image it was minted for instead of silently changing.
    The user_id prefix keeps a user's objects grouped for lifecycle/erasure.
    """
    return f"avatar/{user_id}/{uuid4()}.{extension}"
