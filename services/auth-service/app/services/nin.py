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


def name_parts(
    first_name: str | None, last_name: str | None, full_name: str
) -> tuple[str | None, str | None]:
    """The (first, last) the NIN registry match is scored against.

    Stored parts win when present — they are exactly what the person typed
    against a form that told them to match their NIN slip (SCRUM-231). Only
    an account from before migration 0019, which carries `full_name` alone,
    falls through to the token-splitting heuristic below; a new account never
    does. Every matcher goes through here so the precedence lives in one place.
    """
    first = (first_name or "").strip() or None
    last = (last_name or "").strip() or None
    if first or last:
        return first, last
    return split_full_name(full_name)


def join_name(first_name: str, last_name: str) -> str:
    """The display `full_name` derived from the two parts, with the whitespace
    a person might paste in stripped so the greeting never reads "Ada  Obi"."""
    return " ".join(p for p in (first_name.strip(), last_name.strip()) if p)


def split_full_name(full_name: str) -> tuple[str | None, str | None]:
    """Split a stored full name into (first, last) for the registry match.

    ⚠️ FALLBACK ONLY since SCRUM-231 — reached for accounts that predate
    migration 0019 and carry no stored parts. Go through `name_parts`, never
    call this directly from a matcher.

    ``user_pii.full_name`` is ONE column but the registry match wants the two
    names separately. Nigerian names do not split reliably — three tokens may
    be first+middle+last, or a given name and a two-word surname — so we take
    the first and last tokens and let the provider score each field rather than
    guessing at the middle. A single token is sent as the first name only, and
    a blank name yields ``(None, None)``, degrading the check to "does this NIN
    exist" rather than failing the request.
    """
    parts = full_name.split()
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[-1]


def hash_nin(nin: str) -> str:
    """bcrypt-hash a NIN (per-call salt, cost=12 default)."""
    return bcrypt.hashpw(nin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def lookup_nin(nin: str, *, pepper: str) -> str:
    """Deterministic HMAC-SHA256 hex digest for dedup lookups."""
    return hmac.new(pepper.encode("utf-8"), nin.encode("utf-8"), hashlib.sha256).hexdigest()
