"""PoA document validation + key derivation helpers.

Content type is decided by SNIFFING THE BYTES (magic numbers), not by
trusting the client-supplied filename or Content-Type header — a PoA is a
legal document and the accepted-formats rule (PDF, JPG only) must hold
server-side. Validation errors never echo the document bytes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

# (content_type, extension) keyed by the file's leading magic bytes.
_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"


class InvalidPoaDocument(ValueError):
    """The uploaded file is not an accepted format or violates a size bound.

    Carries a machine code (not the bytes) so the route can map it to a
    specific 422 without ever surfacing document content.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_document_type(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the file's magic bytes.

    Raises InvalidPoaDocument(POA_DOCUMENT_INVALID) for anything that is not
    a PDF or JPEG. The bytes are inspected, never logged or echoed.
    """
    if data.startswith(_PDF_MAGIC):
        return "application/pdf", "pdf"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg", "jpg"
    raise InvalidPoaDocument("POA_DOCUMENT_INVALID", "PoA document must be a PDF or JPEG file.")


def validate_size(data: bytes, *, max_bytes: int) -> None:
    """Reject an empty file or one larger than the configured ceiling."""
    if len(data) == 0:
        raise InvalidPoaDocument("POA_DOCUMENT_INVALID", "PoA document is empty.")
    if len(data) > max_bytes:
        raise InvalidPoaDocument(
            "POA_DOCUMENT_TOO_LARGE",
            f"PoA document exceeds the {max_bytes} byte limit.",
        )


def build_object_key(user_id: UUID, *, extension: str) -> str:
    """Private-bucket key: poa/{user_id}/{uuid}.{ext}.

    The random uuid avoids collisions and makes the key unguessable; the
    user_id prefix keeps a user's documents grouped for lifecycle/erasure.
    """
    return f"poa/{user_id}/{uuid4()}.{extension}"
