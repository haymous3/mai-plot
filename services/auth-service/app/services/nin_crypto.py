"""NIN at-rest encryption (SCRUM-224).

Until this ticket the NIN existed only as two one-way derivations (bcrypt
hash + HMAC lookup, see services/nin.py). Admins now need the number itself
— for support calls, regulator and bank-partner requests, and to correct a
mistyped registration — so a third column, `user_pii.nin_encrypted`, holds
the value under AES-256-GCM. The hash and lookup columns are unchanged and
still do what they did: verify and dedupe.

Format of the stored blob
-------------------------
    byte 0        key version (currently 1)
    bytes 1..12   96-bit random nonce, fresh per encryption
    bytes 13..    ciphertext || 16-byte GCM tag

The version byte is there so a key rotation can be added later without a
schema change: a v2 cipher decrypts v1 rows with the old key and writes v2
rows with the new one. Today only version 1 exists.

The user_id is bound in as GCM associated data, so a ciphertext copied from
one row to another fails to decrypt rather than quietly revealing the
wrong person's NIN.

Key handling
------------
The 256-bit key is derived (SHA-256) from the `nin_encryption_key` passphrase.
Outside `env=local` the shipped default is REFUSED: `build_nin_cipher` raises
rather than encrypting real NINs under a key that lives in the repository.
There is deliberately no "fake" cipher and no plaintext fallback — a broken
key configuration must fail the request, never degrade the storage.
"""

from __future__ import annotations

import hashlib
import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_DEFAULT_KEY = "change-me-to-a-long-random-nin-encryption-key"
_MIN_KEY_CHARS = 32
_KEY_VERSION = 1
_NONCE_BYTES = 12


class NinCipherMisconfigured(RuntimeError):
    """The encryption key is absent, too short, or the repository default,
    in an environment where that is not acceptable."""


class NinDecryptError(ValueError):
    """The blob did not decrypt: wrong key, wrong user, tampered, or an
    unknown key version. The value is never part of the message."""


class NinCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise NinCipherMisconfigured("NIN cipher key must be exactly 32 bytes.")
        self._aead = AESGCM(key)

    def encrypt(self, nin: str, *, user_id: UUID) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, nin.encode("utf-8"), user_id.bytes)
        return bytes([_KEY_VERSION]) + nonce + sealed

    def decrypt(self, blob: bytes, *, user_id: UUID) -> str:
        if len(blob) < 1 + _NONCE_BYTES + 16:
            raise NinDecryptError("NIN ciphertext is truncated.")
        if blob[0] != _KEY_VERSION:
            raise NinDecryptError(f"Unknown NIN key version {blob[0]}.")
        nonce = blob[1 : 1 + _NONCE_BYTES]
        sealed = blob[1 + _NONCE_BYTES :]
        try:
            plain = self._aead.decrypt(nonce, sealed, user_id.bytes)
        except InvalidTag as exc:
            raise NinDecryptError("NIN ciphertext failed authentication.") from exc
        return plain.decode("utf-8")


def build_nin_cipher(*, passphrase: str, env: str) -> NinCipher:
    """Derive the AES key from the configured passphrase.

    `env == "local"` accepts anything, including the default, so a fresh
    checkout and CI work with no secret. Everywhere else the default and
    anything shorter than 32 characters are refused up front.
    """
    if env != "local" and (passphrase == _DEFAULT_KEY or len(passphrase) < _MIN_KEY_CHARS):
        raise NinCipherMisconfigured(
            "NIN_ENCRYPTION_KEY must be set to a random string of at least "
            f"{_MIN_KEY_CHARS} characters outside env=local."
        )
    return NinCipher(hashlib.sha256(passphrase.encode("utf-8")).digest())
