"""Document validation + key derivation.

Listing legal documents are PDF or JPEG. The format is decided by sniffing
the magic bytes, not the client filename/content-type. Validation errors
never echo the document bytes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"


class InvalidDocument(ValueError):
    """The upload is not an accepted format or violates a size bound."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_document_type(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the magic bytes; raise for any
    non PDF/JPEG. Bytes are inspected, never logged or echoed."""
    if data.startswith(_PDF_MAGIC):
        return "application/pdf", "pdf"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg", "jpg"
    raise InvalidDocument("DOCUMENT_FORMAT_INVALID", "Document must be a PDF or JPEG file.")


def validate_size(data: bytes, *, max_bytes: int) -> None:
    if len(data) == 0:
        raise InvalidDocument("DOCUMENT_FORMAT_INVALID", "Uploaded document is empty.")
    if len(data) > max_bytes:
        raise InvalidDocument("DOCUMENT_TOO_LARGE", f"Document exceeds the {max_bytes} byte limit.")


def build_document_key(listing_id: UUID, *, extension: str) -> str:
    """Private-bucket key: listings/{listing_id}/documents/{uuid}.{ext}."""
    return f"listings/{listing_id}/documents/{uuid4()}.{extension}"
