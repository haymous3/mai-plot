"""BVN hashing + format validation.

Two derivations of a BVN, never the BVN itself, are persisted:

* ``hash_bvn`` — bcrypt, salted per row. Verifies a BVN but is not
  queryable. This is the value CLAUDE.md mandates for at-rest storage.
* ``lookup_bvn`` — HMAC-SHA256 with a server-wide pepper. Deterministic,
  so a UNIQUE index can enforce one-BVN-one-account. The pepper makes the
  digest useless without the server secret (an 11-digit BVN has too small
  a keyspace for a plain unsalted hash to resist brute force).

The plaintext BVN is never logged, never returned, and never written to
the database.
"""

from __future__ import annotations

import hashlib
import hmac
import re

import bcrypt

# Nigerian BVN: exactly 11 digits.
_BVN_RE = re.compile(r"^\d{11}$")


class InvalidBvnError(ValueError):
    """Raised when a BVN is not 11 digits. The value is never included."""


def validate_bvn_format(bvn: str) -> None:
    """Raise InvalidBvnError unless `bvn` is exactly 11 digits.

    The offending value is deliberately omitted from the error so a BVN
    can never reach a log line or API error body.
    """
    if not _BVN_RE.fullmatch(bvn):
        raise InvalidBvnError("BVN must be exactly 11 digits.")


def hash_bvn(bvn: str) -> str:
    """bcrypt-hash a BVN (per-call salt, cost=12 default)."""
    return bcrypt.hashpw(bvn.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def lookup_bvn(bvn: str, *, pepper: str) -> str:
    """Deterministic HMAC-SHA256 hex digest for dedup lookups."""
    return hmac.new(pepper.encode("utf-8"), bvn.encode("utf-8"), hashlib.sha256).hexdigest()
