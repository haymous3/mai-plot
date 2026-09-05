"""Registration-number format helpers (SCRUM-207)."""

from __future__ import annotations

import pytest

from app.services.registration_number import (
    PREFIX,
    looks_like_email,
    normalize_registration_number,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MH-R-000123", "MH-R-000123"),
        ("mh-r-000123", "MH-R-000123"),
        ("  MH-R-000123  ", "MH-R-000123"),
        # A realtor reading the number off an email often breaks it into groups.
        ("MH-R-000 123", "MH-R-000123"),
        # Past a million realtors the sequence outgrows six digits; still valid.
        ("MH-R-1234567", "MH-R-1234567"),
    ],
)
def test_normalises_a_valid_number(raw: str, expected: str) -> None:
    assert normalize_registration_number(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "MH-R-",
        "MH-R-12",  # too short to be one of ours
        "MHR-000123",  # missing the separator
        "MH-S-000123",  # not the realtor prefix
        "MH-R-00A123",  # not all digits
        "realtor@example.com",
        "000123",
    ],
)
def test_rejects_anything_else(raw: str) -> None:
    assert normalize_registration_number(raw) is None


def test_prefix_is_the_one_the_migration_writes() -> None:
    """Migration 0015 hard-codes 'MH-R-' (SQL cannot import this module). If the
    constant here changes without the migration, issued numbers stop matching
    normalize() and every realtor login breaks — so pin it."""
    assert PREFIX == "MH-R-"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("realtor@example.com", True),
        ("MH-R-000123", False),
        ("", False),
    ],
)
def test_email_detection_is_just_an_at_sign(raw: str, expected: bool) -> None:
    assert looks_like_email(raw) is expected
