"""Unit tests for realtor credential validation (SCRUM-71)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.credentials import (
    InvalidCredential,
    build_id_object_key,
    detect_id_document_type,
    normalize_esvarbon_number,
    validate_id_size,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("esv/1234", "ESV/1234"),
        ("  RC-00912 ", "RC-00912"),
        ("ESVB12345", "ESVB12345"),
    ],
)
def test_normalize_esvarbon_valid(raw: str, expected: str) -> None:
    assert normalize_esvarbon_number(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "AB", "NOLETTERSORNUMBERS!", "ESV ABCD", "1", "way-too-long-licence-number-value"],
)
def test_normalize_esvarbon_invalid(raw: str) -> None:
    with pytest.raises(InvalidCredential):
        normalize_esvarbon_number(raw)


def test_letters_only_no_digit_rejected() -> None:
    with pytest.raises(InvalidCredential):
        normalize_esvarbon_number("ABCDEF")


def test_detect_id_document_type() -> None:
    assert detect_id_document_type(b"%PDF-1.4 ...") == ("application/pdf", "pdf")
    assert detect_id_document_type(b"\xff\xd8\xff\xe0xx") == ("image/jpeg", "jpg")
    assert detect_id_document_type(b"\x89PNG\r\n\x1a\nxx") == ("image/png", "png")


def test_detect_id_document_type_rejects_other() -> None:
    with pytest.raises(InvalidCredential):
        detect_id_document_type(b"GIF89a not allowed")


def test_validate_id_size() -> None:
    validate_id_size(b"abc", max_bytes=10)
    with pytest.raises(InvalidCredential):
        validate_id_size(b"", max_bytes=10)
    with pytest.raises(InvalidCredential):
        validate_id_size(b"abcdefghijk", max_bytes=10)


def test_build_id_object_key() -> None:
    uid = uuid4()
    key = build_id_object_key(uid, extension="pdf")
    assert key.startswith(f"realtor-id/{uid}/")
    assert key.endswith(".pdf")
