"""Realtor credential validation + key derivation (SCRUM-71).

ESVARBON (Estate Surveyors and Valuers Registration Board of Nigeria) licence
numbers are format-validated and normalised. The government-ID file's type is
decided by SNIFFING THE BYTES (magic numbers), not the client-supplied filename
or Content-Type — server-side, accepting PDF / JPEG / PNG only. Validation
errors never echo the document bytes.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

# A licence reference: letters/digits with optional / or - separators, 5-20
# chars, and at least one digit (a registration number is numbered).
_ESVARBON_RE = re.compile(r"^[A-Z0-9][A-Z0-9/-]{3,19}$")

_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class InvalidCredential(ValueError):
    """A credential field or file is malformed. Carries a machine code (never the
    bytes) so the route maps it to a specific 422."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_esvarbon_number(raw: str) -> str:
    """Validate + canonicalise an ESVARBON licence number (trim, upper-case).
    Raises InvalidCredential(ESVARBON_INVALID) on a malformed value."""
    cleaned = raw.strip().upper()
    if not _ESVARBON_RE.match(cleaned) or not any(c.isdigit() for c in cleaned):
        raise InvalidCredential("ESVARBON_INVALID", "ESVARBON licence number format is invalid.")
    return cleaned


def detect_id_document_type(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the file's magic bytes. Accepts PDF,
    JPEG, PNG; raises InvalidCredential(ID_DOCUMENT_INVALID) otherwise."""
    if data.startswith(_PDF_MAGIC):
        return "application/pdf", "pdf"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg", "jpg"
    if data.startswith(_PNG_MAGIC):
        return "image/png", "png"
    raise InvalidCredential(
        "ID_DOCUMENT_INVALID", "Government ID must be a PDF, JPEG, or PNG file."
    )


def validate_id_size(data: bytes, *, max_bytes: int) -> None:
    if len(data) == 0:
        raise InvalidCredential("ID_DOCUMENT_INVALID", "Government ID file is empty.")
    if len(data) > max_bytes:
        raise InvalidCredential(
            "ID_DOCUMENT_TOO_LARGE", f"Government ID exceeds the {max_bytes} byte limit."
        )


def build_id_object_key(user_id: UUID, *, extension: str) -> str:
    """Private-bucket key: realtor-id/{user_id}/{uuid}.{ext}."""
    return f"realtor-id/{user_id}/{uuid4()}.{extension}"
