"""Phone normalisation — covers the three accepted formats and rejection
of landline / non-Nigerian / malformed inputs."""

from __future__ import annotations

import pytest

from app.validators.phone import InvalidPhoneError, normalise_nigerian_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+2348012345678", "+2348012345678"),
        ("2348012345678", "+2348012345678"),
        ("08012345678", "+2348012345678"),
        ("+234 801 234 5678", "+2348012345678"),
        ("0801-234-5678", "+2348012345678"),
        ("(0801) 234 5678", "+2348012345678"),
        ("07012345678", "+2347012345678"),
        ("09012345678", "+2349012345678"),
    ],
)
def test_normalises_accepted_formats(raw: str, expected: str) -> None:
    assert normalise_nigerian_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345",
        "+1 555 123 4567",  # US number
        "+44 20 7946 0958",  # UK landline
        "08012345",  # too short
        "0801234567890",  # too long
        "+2341234567890",  # prefix 1 not in 7/8/9
        "+2346012345678",  # prefix 6 not in 7/8/9
        "abc",
    ],
)
def test_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalise_nigerian_phone(raw)
