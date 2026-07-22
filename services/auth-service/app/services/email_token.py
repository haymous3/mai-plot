"""Email magic-link token generation + hashing (SCRUM-152).

Unlike the 6-digit OTP (bcrypt, because it is low-entropy and guessable),
a magic-link token is a 256-bit URL-safe random value. Brute force is not a
threat, so we store a fast, indexable SHA-256 digest rather than bcrypt —
this lets the verify path look the token up by its hash in one indexed query
instead of scanning and bcrypt-comparing every candidate.
"""

from __future__ import annotations

import hashlib
import secrets

# 32 bytes = 256 bits of entropy; token_urlsafe yields ~43 URL-safe chars.
_TOKEN_BYTES = 32


def generate_token() -> str:
    """Return a fresh URL-safe 256-bit token to embed in the magic link."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token — what we persist and look up by."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
