"""Unit tests for the keyset pagination cursor (SCRUM-82)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.services.cursor import CursorInvalid, decode_cursor, encode_cursor


def test_round_trip_preserves_created_at_and_id() -> None:
    created = datetime(2026, 6, 22, 14, 30, 5, 123456, tzinfo=UTC)
    ident = uuid4()
    cursor = decode_cursor(encode_cursor(created, ident))
    assert cursor.created_at == created
    assert cursor.id == ident


def test_cursor_is_opaque_base64() -> None:
    token = encode_cursor(datetime(2026, 1, 1, tzinfo=UTC), uuid4())
    # No raw separator / timestamp characters leak through.
    assert "|" not in token
    assert ":" not in token


def test_decode_rejects_garbage() -> None:
    with pytest.raises(CursorInvalid):
        decode_cursor("not-a-real-cursor!!!")


def test_decode_rejects_well_formed_base64_with_bad_payload() -> None:
    import base64

    bad = base64.urlsafe_b64encode(b"missing-separator").decode("ascii")
    with pytest.raises(CursorInvalid):
        decode_cursor(bad)


def test_decode_rejects_bad_uuid() -> None:
    import base64

    bad = base64.urlsafe_b64encode(b"2026-01-01T00:00:00+00:00|not-a-uuid").decode("ascii")
    with pytest.raises(CursorInvalid):
        decode_cursor(bad)
