"""Email normalisation + format check (SCRUM-152)."""

from __future__ import annotations

import pytest

from app.validators.email import InvalidEmailError, normalise_email


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("buyer@example.com", "buyer@example.com"),
        ("  Buyer@Example.COM ", "buyer@example.com"),
        ("a.b+tag@sub.domain.ng", "a.b+tag@sub.domain.ng"),
    ],
)
def test_normalise_valid(raw: str, expected: str) -> None:
    assert normalise_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "no-at-sign",
        "no@tld",
        "spaces in@email.com",
        "two@@example.com",
        "@example.com",
        "buyer@.com",
    ],
)
def test_normalise_rejects_junk(raw: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalise_email(raw)


def test_normalise_rejects_overlong_address() -> None:
    local = "a" * 250
    with pytest.raises(InvalidEmailError):
        normalise_email(f"{local}@example.com")
