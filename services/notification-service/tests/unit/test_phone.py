"""Unit tests for Nigerian MSISDN normalisation (SCRUM-80)."""

from __future__ import annotations

import pytest

from app.services.phone import InvalidPhoneNumber, normalize_ng_msisdn


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("08031234567", "+2348031234567"),  # national, 0-prefixed
        ("07011234567", "+2347011234567"),
        ("09091234567", "+2349091234567"),
        ("2348031234567", "+2348031234567"),  # international, no +
        ("+2348031234567", "+2348031234567"),  # already canonical
        ("8031234567", "+2348031234567"),  # bare 10-digit
        ("+234 803 123 4567", "+2348031234567"),  # separators stripped
        ("0803-123-4567", "+2348031234567"),
    ],
)
def test_normalizes_valid_numbers(raw: str, expected: str) -> None:
    assert normalize_ng_msisdn(raw) == expected


def test_canonical_form_is_idempotent() -> None:
    once = normalize_ng_msisdn("08031234567")
    assert normalize_ng_msisdn(once) == once


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "0123456789",  # national part starts 1, not 7/8/9
        "08031234",  # too short
        "080312345678",  # too long
        "+15551234567",  # not Nigerian
        "notaphone",
        "+234803123456a",  # non-digit
    ],
)
def test_rejects_invalid_numbers(raw: str | None) -> None:
    with pytest.raises(InvalidPhoneNumber):
        normalize_ng_msisdn(raw)
