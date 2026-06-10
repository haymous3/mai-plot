"""NIN hashing + format helpers."""

from __future__ import annotations

import pytest

from app.services.nin import InvalidNinError, hash_nin, lookup_nin, validate_nin_format

_NIN = "12345678901"


def test_validate_accepts_11_digits() -> None:
    validate_nin_format(_NIN)  # no raise


@pytest.mark.parametrize("bad", ["1234567890", "123456789012", "abcdefghijk", "", "1234567890a"])
def test_validate_rejects_bad_format(bad: str) -> None:
    with pytest.raises(InvalidNinError):
        validate_nin_format(bad)


def test_validate_error_never_contains_the_value() -> None:
    try:
        validate_nin_format("88888888888888")
    except InvalidNinError as exc:
        assert "8888" not in str(exc)


def test_hash_is_bcrypt_and_not_plaintext() -> None:
    hashed = hash_nin(_NIN)
    assert hashed != _NIN
    assert hashed.startswith("$2")


def test_hash_is_salted_per_call() -> None:
    assert hash_nin(_NIN) != hash_nin(_NIN)


def test_lookup_is_deterministic_for_same_pepper() -> None:
    assert lookup_nin(_NIN, pepper="pepper-a") == lookup_nin(_NIN, pepper="pepper-a")


def test_lookup_depends_on_pepper() -> None:
    assert lookup_nin(_NIN, pepper="pepper-a") != lookup_nin(_NIN, pepper="pepper-b")


def test_lookup_is_sha256_hex() -> None:
    digest = lookup_nin(_NIN, pepper="p")
    assert len(digest) == 64
    int(digest, 16)  # valid hex
