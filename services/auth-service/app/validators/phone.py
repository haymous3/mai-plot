"""Nigerian phone number normalisation.

Accepts the three common formats Nigerians type:
  +234 8012345678
  234 8012345678
  0801 234 5678
…and returns canonical E.164 form +234XXXXXXXXXX.

Only MTN/Glo/Airtel/9mobile prefixes that start with 7, 8, or 9 after
the country code are accepted; landline ranges are out of scope for
the OTP flow.
"""

from __future__ import annotations

import re

_NIGERIAN_E164 = re.compile(r"^\+234[789]\d{9}$")


class InvalidPhoneError(ValueError):
    """Raised when a phone string cannot be normalised to Nigerian E.164."""


def normalise_nigerian_phone(raw: str) -> str:
    """Return the canonical +234XXXXXXXXXX form or raise InvalidPhoneError.

    Strips whitespace, dashes, and parentheses, then folds the three
    accepted prefix variants into E.164.
    """
    if not raw:
        raise InvalidPhoneError("phone is empty")

    stripped = re.sub(r"[\s\-()]+", "", raw)

    if stripped.startswith("+234"):
        candidate = stripped
    elif stripped.startswith("234"):
        candidate = "+" + stripped
    elif stripped.startswith("0") and len(stripped) == 11:
        candidate = "+234" + stripped[1:]
    else:
        raise InvalidPhoneError(f"unrecognised Nigerian phone format: {raw!r}")

    if not _NIGERIAN_E164.match(candidate):
        raise InvalidPhoneError(f"not a valid Nigerian mobile number: {raw!r}")

    return candidate
