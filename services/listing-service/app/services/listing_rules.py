"""Shared listing business rules (used by create + update).

Keeping the urgency/expiry rule in one place stops create and PATCH from
drifting: distress sales require a valid urgency tag and expire at the end of
that window; normal sales ignore any urgency tag and run 90 days (business
rules §2/§3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Distress urgency window -> days. Also the set of valid distress tags.
URGENCY_DAYS = {"7_days": 7, "14_days": 14, "30_days": 30}

# Normal sales stay active for 90 days, renewable (business rule §3).
NORMAL_SALE_DAYS = 90


class InvalidUrgency(ValueError):
    """A distress sale has no valid urgency tag."""


def resolve_urgency_and_expiry(
    *, sale_type: str, urgency_tag: str | None
) -> tuple[str | None, datetime]:
    """Validate the urgency tag against sale_type and derive the expiry.

    Distress: requires a valid tag, expires at the end of that window.
    Normal: drops any tag (DB CHECK requires NULL) and runs 90 days.
    """
    now = datetime.now(UTC)
    if sale_type == "distress":
        if urgency_tag not in URGENCY_DAYS:
            raise InvalidUrgency()
        return urgency_tag, now + timedelta(days=URGENCY_DAYS[urgency_tag])
    return None, now + timedelta(days=NORMAL_SALE_DAYS)
