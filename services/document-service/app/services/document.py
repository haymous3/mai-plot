"""Document validation + key derivation.

Listing legal documents are PDF or JPEG. The format is decided by sniffing
the magic bytes, not the client filename/content-type. Validation errors
never echo the document bytes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class InvalidDocument(ValueError):
    """The upload is not an accepted format or violates a size bound."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_document_type(data: bytes, *, allow_png: bool = False) -> tuple[str, str]:
    """Return (content_type, extension) from the magic bytes. Listing legal docs
    are PDF/JPEG; buyer loan docs (SCRUM-131) also allow PNG via allow_png. Bytes
    are inspected, never logged or echoed."""
    if data.startswith(_PDF_MAGIC):
        return "application/pdf", "pdf"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg", "jpg"
    if allow_png and data.startswith(_PNG_MAGIC):
        return "image/png", "png"
    accepted = "PDF, JPEG, or PNG" if allow_png else "PDF or JPEG"
    raise InvalidDocument("DOCUMENT_FORMAT_INVALID", f"Document must be a {accepted} file.")


def validate_size(data: bytes, *, max_bytes: int) -> None:
    if len(data) == 0:
        raise InvalidDocument("DOCUMENT_FORMAT_INVALID", "Uploaded document is empty.")
    if len(data) > max_bytes:
        raise InvalidDocument("DOCUMENT_TOO_LARGE", f"Document exceeds the {max_bytes} byte limit.")


def build_document_key(listing_id: UUID, *, extension: str) -> str:
    """Private-bucket key: listings/{listing_id}/documents/{uuid}.{ext}."""
    return f"listings/{listing_id}/documents/{uuid4()}.{extension}"


def build_loan_document_key(loan_id: UUID, *, extension: str) -> str:
    """Private-bucket key: loans/{loan_id}/documents/{uuid}.{ext} (SCRUM-131)."""
    return f"loans/{loan_id}/documents/{uuid4()}.{extension}"


def build_user_document_key(user_id: UUID, *, extension: str) -> str:
    """Private-bucket key: users/{user_id}/documents/{uuid}.{ext} (SCRUM-188).

    Keyed by the OWNER rather than by a listing or loan, because a personal
    document belongs to the person and outlives both. The user_id prefix also
    keeps everything one subject owns under a single path, which is what makes
    an NDPR erasure request tractable.
    """
    return f"users/{user_id}/documents/{uuid4()}.{extension}"
