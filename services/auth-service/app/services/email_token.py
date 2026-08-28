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


def build_verify_url(base_url: str, token: str) -> str:
    """Compose the magic link the email carries: base_url with ?token= appended.

    The frontend landing page reads the token from the query string and POSTs it
    to the service (so the token stays out of server logs). The base_url is what
    decides which flow the link belongs to — registration and resend pass the
    verification page, password reset (SCRUM-191) passes the reset page."""
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}token={token}"
