"""BVN hashing + format helpers."""

from __future__ import annotations

import pytest

from app.services.bvn import InvalidBvnError, hash_bvn, lookup_bvn, validate_bvn_format

_BVN = "12345678901"


def test_validate_accepts_11_digits() -> None:
    validate_bvn_format(_BVN)  # no raise


@pytest.mark.parametrize("bad", ["1234567890", "123456789012", "abcdefghijk", "", "1234567890a"])
def test_validate_rejects_bad_format(bad: str) -> None:
    with pytest.raises(InvalidBvnError):
        validate_bvn_format(bad)


def test_validate_error_never_contains_the_value() -> None:
    try:
        validate_bvn_format("99999999999999")
    except InvalidBvnError as exc:
        assert "9999" not in str(exc)


def test_hash_is_bcrypt_and_not_plaintext() -> None:
    hashed = hash_bvn(_BVN)
    assert hashed != _BVN
    assert hashed.startswith("$2")


def test_hash_is_salted_per_call() -> None:
    assert hash_bvn(_BVN) != hash_bvn(_BVN)


def test_lookup_is_deterministic_for_same_pepper() -> None:
    assert lookup_bvn(_BVN, pepper="pepper-a") == lookup_bvn(_BVN, pepper="pepper-a")


def test_lookup_depends_on_pepper() -> None:
    assert lookup_bvn(_BVN, pepper="pepper-a") != lookup_bvn(_BVN, pepper="pepper-b")


def test_lookup_differs_per_bvn() -> None:
    assert lookup_bvn(_BVN, pepper="p") != lookup_bvn("10987654321", pepper="p")


def test_lookup_is_sha256_hex() -> None:
    digest = lookup_bvn(_BVN, pepper="p")
    assert len(digest) == 64
    int(digest, 16)  # valid hex
