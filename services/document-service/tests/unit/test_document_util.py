"""Document validation + key derivation helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.document import (
    InvalidDocument,
    build_document_key,
    detect_document_type,
    validate_size,
)

_PDF = b"%PDF-1.7 deed of assignment"
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF scanned c of o"


def test_detects_pdf() -> None:
    assert detect_document_type(_PDF) == ("application/pdf", "pdf")


def test_detects_jpeg() -> None:
    assert detect_document_type(_JPEG) == ("image/jpeg", "jpg")


@pytest.mark.parametrize("bad", [b"GIF89a...", b"PK\x03\x04 zip", b"plain text"])
def test_rejects_non_pdf_jpeg(bad: bytes) -> None:
    with pytest.raises(InvalidDocument) as exc:
        detect_document_type(bad)
    assert exc.value.code == "DOCUMENT_FORMAT_INVALID"


def test_validate_size_accepts_within_limit() -> None:
    validate_size(_PDF, max_bytes=1024)


def test_validate_size_rejects_empty() -> None:
    with pytest.raises(InvalidDocument) as exc:
        validate_size(b"", max_bytes=1024)
    assert exc.value.code == "DOCUMENT_FORMAT_INVALID"


def test_validate_size_rejects_too_large() -> None:
    with pytest.raises(InvalidDocument) as exc:
        validate_size(b"x" * 11, max_bytes=10)
    assert exc.value.code == "DOCUMENT_TOO_LARGE"


def test_error_never_contains_bytes() -> None:
    try:
        detect_document_type(b"secret deed text")
    except InvalidDocument as exc:
        assert "secret" not in str(exc)


def test_document_key_shape() -> None:
    listing_id = uuid4()
    key = build_document_key(listing_id, extension="pdf")
    assert key.startswith(f"listings/{listing_id}/documents/")
    assert key.endswith(".pdf")
