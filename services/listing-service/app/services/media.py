"""Media validation + key derivation.

The media kind is decided by SNIFFING THE BYTES (magic numbers), not by
trusting the client-declared media_type or filename, and the declared type
must match what the bytes actually are. Photos are JPEG/PNG; videos are
MP4 (ISO base-media `ftyp`). Validation errors never echo the bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class InvalidMedia(ValueError):
    """The upload is not an accepted format, mismatches its declared type, or
    violates a size bound. Carries a machine code (never the bytes)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MediaInfo:
    kind: str  # 'photo' | 'video'
    content_type: str
    extension: str


def _sniff(data: bytes) -> MediaInfo | None:
    if data.startswith(_JPEG_MAGIC):
        return MediaInfo(kind="photo", content_type="image/jpeg", extension="jpg")
    if data.startswith(_PNG_MAGIC):
        return MediaInfo(kind="photo", content_type="image/png", extension="png")
    # MP4 / ISO base media: a `ftyp` box begins at byte offset 4.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return MediaInfo(kind="video", content_type="video/mp4", extension="mp4")
    return None


def validate_media(
    data: bytes,
    *,
    declared_type: str,
    max_photo_bytes: int,
    max_video_bytes: int,
) -> MediaInfo:
    """Validate the bytes against the declared media_type and size limits.

    Raises InvalidMedia (-> 422) for an unrecognised format, a type that does
    not match the bytes, an empty file, or an over-size file.
    """
    if len(data) == 0:
        raise InvalidMedia("MEDIA_FORMAT_INVALID", "Uploaded media is empty.")
    info = _sniff(data)
    if info is None:
        raise InvalidMedia(
            "MEDIA_FORMAT_INVALID", "Media must be a JPEG/PNG photo or an MP4 video."
        )
    if info.kind != declared_type:
        raise InvalidMedia(
            "MEDIA_TYPE_MISMATCH", f"File is a {info.kind}, not the declared {declared_type}."
        )
    limit = max_photo_bytes if info.kind == "photo" else max_video_bytes
    if len(data) > limit:
        raise InvalidMedia("MEDIA_TOO_LARGE", f"{info.kind} exceeds the {limit} byte limit.")
    return info


def build_media_key(listing_id: UUID, *, extension: str) -> str:
    """Public-bucket key: listings/{listing_id}/media/{uuid}.{ext}."""
    return f"listings/{listing_id}/media/{uuid4()}.{extension}"
