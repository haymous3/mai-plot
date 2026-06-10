"""NIN hashing + format validation.

Mirrors services/bvn.py. Two non-reversible derivations of a NIN are
stored, never the NIN itself:

* ``hash_nin`` — bcrypt, salted per row (at-rest verify hash).
* ``lookup_nin`` — HMAC-SHA256 with a server pepper, deterministic, so a
  UNIQUE index enforces one-NIN-one-account.

The plaintext NIN is never logged, returned, or written to the database.
"""

from __future__ import annotations

import hashlib
import hmac
import re

import bcrypt

# Nigerian NIN: exactly 11 digits.
_NIN_RE = re.compile(r"^\d{11}$")


class InvalidNinError(ValueError):
    """Raised when a NIN is not 11 digits. The value is never included."""


def validate_nin_format(nin: str) -> None:
    """Raise InvalidNinError unless `nin` is exactly 11 digits.

    The offending value is omitted from the error so a NIN can never reach
    a log line or API error body.
    """
    if not _NIN_RE.fullmatch(nin):
        raise InvalidNinError("NIN must be exactly 11 digits.")


def hash_nin(nin: str) -> str:
    """bcrypt-hash a NIN (per-call salt, cost=12 default)."""
    return bcrypt.hashpw(nin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def lookup_nin(nin: str, *, pepper: str) -> str:
    """Deterministic HMAC-SHA256 hex digest for dedup lookups."""
    return hmac.new(pepper.encode("utf-8"), nin.encode("utf-8"), hashlib.sha256).hexdigest()
