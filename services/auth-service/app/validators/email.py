"""Email normalisation + a pragmatic format check.

A full RFC 5322 validator is overkill (and famously hard) for a signup
field — the real proof an address exists is that the verification email
lands. So we lower-case + strip, then apply a conservative regex that
rejects the obvious junk (no @, spaces, missing TLD). This keeps a new
dependency (email-validator / pydantic[email]) out of the service.
"""

from __future__ import annotations

import re

# One @, a non-empty local part, a dotted domain with a 2+ char TLD.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class InvalidEmailError(ValueError):
    """Raised when a string is not a plausible email address."""


def normalise_email(raw: str) -> str:
    """Return the trimmed, lower-cased address or raise InvalidEmailError."""
    if not raw:
        raise InvalidEmailError("email is empty")
    candidate = raw.strip().lower()
    if len(candidate) > 254 or not _EMAIL_RE.match(candidate):
        raise InvalidEmailError(f"not a valid email address: {raw!r}")
    return candidate
