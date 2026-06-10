"""PoA document validation + key derivation helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.poa import (
    InvalidPoaDocument,
    build_object_key,
    detect_document_type,
    validate_size,
)

_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3 body"
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF body"


def test_detects_pdf() -> None:
    assert detect_document_type(_PDF) == ("application/pdf", "pdf")


def test_detects_jpeg() -> None:
    assert detect_document_type(_JPEG) == ("image/jpeg", "jpg")


@pytest.mark.parametrize("bad", [b"GIF89a....", b"PK\x03\x04 zip", b"hello world", b"\x00\x01\x02"])
def test_rejects_non_pdf_jpeg(bad: bytes) -> None:
    with pytest.raises(InvalidPoaDocument) as exc:
        detect_document_type(bad)
    assert exc.value.code == "POA_DOCUMENT_INVALID"


def test_validate_size_accepts_within_limit() -> None:
    validate_size(_PDF, max_bytes=1024)  # no raise


def test_validate_size_rejects_empty() -> None:
    with pytest.raises(InvalidPoaDocument) as exc:
        validate_size(b"", max_bytes=1024)
    assert exc.value.code == "POA_DOCUMENT_INVALID"


def test_validate_size_rejects_too_large() -> None:
    with pytest.raises(InvalidPoaDocument) as exc:
        validate_size(b"x" * 11, max_bytes=10)
    assert exc.value.code == "POA_DOCUMENT_TOO_LARGE"


def test_error_never_contains_the_document_bytes() -> None:
    secret = b"\x13\x37 super secret contract text"
    try:
        detect_document_type(secret)
    except InvalidPoaDocument as exc:
        assert "secret" not in str(exc)
        assert "contract" not in str(exc)


def test_object_key_shape() -> None:
    user_id = uuid4()
    key = build_object_key(user_id, extension="pdf")
    assert key.startswith(f"poa/{user_id}/")
    assert key.endswith(".pdf")


def test_object_keys_are_unique_per_call() -> None:
    user_id = uuid4()
    assert build_object_key(user_id, extension="jpg") != build_object_key(user_id, extension="jpg")
