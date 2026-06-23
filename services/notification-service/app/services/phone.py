"""Nigerian mobile number validation + normalisation (SCRUM-80).

SMS must only be sent to a well-formed Nigerian MSISDN (AC: "Nigerian phone
number format validated before sending"). `normalize_ng_msisdn` accepts the
formats users and other services store phones in and returns the canonical
E.164 form (`+234` + 10 national digits) that Termii expects. Anything that
isn't a plausible NG mobile number raises InvalidPhoneNumber — the send path
treats that as a permanent (non-retryable) failure.

Nigerian mobile national numbers are 10 digits beginning 7, 8, or 9 (e.g.
0803…, 0701…, 0905…). We accept them with a `0` prefix (national), a `234` or
`+234` prefix (international), or bare.
"""

from __future__ import annotations

import re

# After stripping separators, the 10-digit national number (no leading 0) must
# start 7/8/9 then 9 more digits.
_NATIONAL_10 = re.compile(r"^[789]\d{9}$")
_SEPARATORS = re.compile(r"[\s\-()]")


class InvalidPhoneNumber(ValueError):
    """The supplied string is not a valid Nigerian mobile number."""


def normalize_ng_msisdn(raw: str | None) -> str:
    """Return the canonical `+234XXXXXXXXXX` form, or raise InvalidPhoneNumber.

    Idempotent: a value already in canonical form passes straight through."""
    if raw is None:
        raise InvalidPhoneNumber("phone number is missing")

    cleaned = _SEPARATORS.sub("", raw.strip())
    if not cleaned:
        raise InvalidPhoneNumber("phone number is empty")

    if cleaned.startswith("+234"):
        national = cleaned[4:]
    elif cleaned.startswith("234"):
        national = cleaned[3:]
    elif cleaned.startswith("0"):
        national = cleaned[1:]
    else:
        national = cleaned

    if not _NATIONAL_10.match(national):
        raise InvalidPhoneNumber(f"not a valid Nigerian mobile number: {raw!r}")
    return f"+234{national}"
