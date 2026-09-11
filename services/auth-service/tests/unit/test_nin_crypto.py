"""NIN at-rest cipher (SCRUM-224)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.nin_crypto import (
    NinCipherMisconfigured,
    NinDecryptError,
    build_nin_cipher,
)

_NIN = "12345678901"
_DEFAULT = "change-me-to-a-long-random-nin-encryption-key"
# Obviously synthetic: GitGuardian scans every commit and flags a realistic
# looking literal as a "Generic Password". Length is what the gate checks.
_STRONG = "a" * 40


def test_round_trip_and_ciphertext_hides_the_value() -> None:
    cipher = build_nin_cipher(passphrase=_STRONG, env="local")
    user_id = uuid4()

    blob = cipher.encrypt(_NIN, user_id=user_id)

    assert blob[0] == 1  # key version
    assert _NIN.encode() not in blob
    assert cipher.decrypt(blob, user_id=user_id) == _NIN


def test_fresh_nonce_per_encryption() -> None:
    cipher = build_nin_cipher(passphrase=_STRONG, env="local")
    user_id = uuid4()
    assert cipher.encrypt(_NIN, user_id=user_id) != cipher.encrypt(_NIN, user_id=user_id)


def test_ciphertext_is_bound_to_the_user() -> None:
    """A blob copied from one row to another must not open — the user_id is
    GCM associated data."""
    cipher = build_nin_cipher(passphrase=_STRONG, env="local")
    blob = cipher.encrypt(_NIN, user_id=uuid4())
    with pytest.raises(NinDecryptError):
        cipher.decrypt(blob, user_id=uuid4())


def test_tampering_is_detected() -> None:
    cipher = build_nin_cipher(passphrase=_STRONG, env="local")
    user_id = uuid4()
    blob = bytearray(cipher.encrypt(_NIN, user_id=user_id))
    blob[-1] ^= 0x01
    with pytest.raises(NinDecryptError):
        cipher.decrypt(bytes(blob), user_id=user_id)


def test_wrong_key_does_not_decrypt() -> None:
    user_id = uuid4()
    blob = build_nin_cipher(passphrase=_STRONG, env="local").encrypt(_NIN, user_id=user_id)
    other = build_nin_cipher(passphrase=_STRONG + "-rotated", env="local")
    with pytest.raises(NinDecryptError):
        other.decrypt(blob, user_id=user_id)


def test_unknown_version_and_truncated_blob_are_refused() -> None:
    cipher = build_nin_cipher(passphrase=_STRONG, env="local")
    user_id = uuid4()
    blob = cipher.encrypt(_NIN, user_id=user_id)
    with pytest.raises(NinDecryptError):
        cipher.decrypt(bytes([2]) + blob[1:], user_id=user_id)
    with pytest.raises(NinDecryptError):
        cipher.decrypt(blob[:10], user_id=user_id)


def test_local_accepts_the_default_key() -> None:
    assert build_nin_cipher(passphrase=_DEFAULT, env="local") is not None


@pytest.mark.parametrize("env", ["staging", "production"])
def test_non_local_refuses_the_default_key(env: str) -> None:
    with pytest.raises(NinCipherMisconfigured):
        build_nin_cipher(passphrase=_DEFAULT, env=env)


def test_non_local_refuses_a_short_key() -> None:
    with pytest.raises(NinCipherMisconfigured):
        build_nin_cipher(passphrase="short", env="production")


def test_non_local_accepts_a_strong_key() -> None:
    assert build_nin_cipher(passphrase=_STRONG, env="production") is not None
