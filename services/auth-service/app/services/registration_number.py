"""Maihomme realtor registration-number format (SCRUM-207).

One place that knows what a registration number looks like, so the login path
and the issuance path cannot disagree.

`MH-R-` + a zero-padded sequence value, e.g. `MH-R-000123`. The VALUE is minted
by Postgres (`realtor_registration_number_seq`, inside the INSERT) — this module
only recognises and canonicalises one, it never generates one. That split is
deliberate: a Python-side generator would need a uniqueness retry loop, and the
sequence makes collisions impossible by construction.

⚠️ The same prefix is written literally in migration 0015 (SQL cannot import
this). tests/integration/test_realtor_registration_number.py asserts an issued
number satisfies `normalize()` here, so the two cannot drift silently.
"""

from __future__ import annotations

import re

PREFIX = "MH-R-"

# The digits are only padded TO six — a platform with a million realtors keeps
# issuing valid numbers, so the ceiling is generous rather than exactly six.
_PATTERN = re.compile(rf"^{re.escape(PREFIX)}\d{{4,12}}$")


def normalize_registration_number(raw: str) -> str | None:
    """Canonicalise a user-typed registration number, or None if it is not one.

    Upper-cases and strips surrounding whitespace, and tolerates the spaces a
    realtor reading the number off an email tends to introduce. Returns None
    rather than raising: at the login call site "not a registration number" and
    "no such registration number" must be indistinguishable to the client.
    """
    cleaned = raw.strip().upper().replace(" ", "")
    return cleaned if _PATTERN.match(cleaned) else None


def looks_like_email(raw: str) -> bool:
    """Whether a login identifier should be resolved as an email address.

    Deliberately just "contains an @": a registration number never does, and
    anything else is left to the email lookup to reject. Full RFC validation
    here would only add ways for a legitimate address to be misrouted.
    """
    return "@" in raw
