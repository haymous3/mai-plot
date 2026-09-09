"""Realtor upload validation + key derivation (SCRUM-71).

An uploaded file's type is decided by SNIFFING THE BYTES (magic numbers), not the
client-supplied filename or Content-Type. Validation errors never echo the file's
bytes.

What is left here is the INSPECTION REPORT media — photos and video — plus the
base-location coordinate check. Realtor onboarding itself no longer validates
anything but coverage:

⚠️ ESVARBON validation was REMOVED here by SCRUM-207. Realtors are no longer
asked for a licence number — the admin verifies the application and the platform
issues a Maihomme registration number (auth-service) instead — so the normaliser
had no caller left. `realtors.esvarbon_number` still holds the values collected
before the change; nothing validates a new one because nothing accepts one.

⚠️ The GOVERNMENT-ID helpers (`detect_id_document_type`, `validate_id_size`,
`build_id_object_key`) went the same way in SCRUM-219. Onboarding stopped
collecting the "Professional Credentials" document and the admin viewer that read
it back was removed, so all three lost their only callers.
"""

from __future__ import annotations

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class InvalidCredential(ValueError):
    """A credential field or file is malformed. Carries a machine code (never the
    bytes) so the route maps it to a specific 422."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_coordinates(lat: float, lng: float) -> None:
    """Reject out-of-range lat/lng (SCRUM-72 base location)."""
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        raise InvalidCredential("LOCATION_INVALID", "Base location coordinates are out of range.")


def detect_photo_type(data: bytes) -> tuple[str, str]:
    """(content_type, extension) for an inspection photo — JPEG/PNG only (SCRUM-73).
    Raises InvalidCredential(PHOTO_INVALID) otherwise."""
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg", "jpg"
    if data.startswith(_PNG_MAGIC):
        return "image/png", "png"
    raise InvalidCredential("PHOTO_INVALID", "Inspection photos must be JPEG or PNG.")


def validate_photo_size(data: bytes, *, max_bytes: int) -> None:
    if len(data) == 0:
        raise InvalidCredential("PHOTO_INVALID", "An inspection photo is empty.")
    if len(data) > max_bytes:
        raise InvalidCredential("PHOTO_TOO_LARGE", f"A photo exceeds the {max_bytes} byte limit.")


_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"


def detect_video_type(data: bytes) -> tuple[str, str]:
    """(content_type, extension) for an optional inspection video — MP4/MOV
    (ISO-BMFF 'ftyp' box) or WebM only (SCRUM-142). Type is sniffed from the
    bytes, not the client filename. Raises InvalidCredential(VIDEO_INVALID)."""
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4", "mp4"
    if data.startswith(_WEBM_MAGIC):
        return "video/webm", "webm"
    raise InvalidCredential("VIDEO_INVALID", "Inspection video must be an MP4 or WebM file.")


def validate_video_size(data: bytes, *, max_bytes: int) -> None:
    if len(data) == 0:
        raise InvalidCredential("VIDEO_INVALID", "The inspection video is empty.")
    if len(data) > max_bytes:
        raise InvalidCredential("VIDEO_TOO_LARGE", f"The video exceeds the {max_bytes} byte limit.")
