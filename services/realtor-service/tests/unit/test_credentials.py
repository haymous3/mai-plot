"""Unit tests for realtor credential validation (SCRUM-71)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.credentials import (
    InvalidCredential,
    build_id_object_key,
    detect_id_document_type,
    validate_id_size,
)

# The ESVARBON normaliser and its tests were removed by SCRUM-207: realtors are
# no longer asked for a licence number, so nothing validated one any more.


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
