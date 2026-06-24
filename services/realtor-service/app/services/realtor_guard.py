"""Realtor eligibility guard (SCRUM-71).

A realtor must be 'approved' (not pending/rejected/suspended) to receive or
accept inspection assignments. This pure check is the contract the
auto-assignment + acceptance flow (SCRUM-72/73) consumes — keeping the
"suspended realtors cannot accept assignments" rule in one place.
"""

from __future__ import annotations

_ELIGIBLE_STATUS = "approved"


def can_accept_assignments(approval_status: str) -> bool:
    return approval_status == _ELIGIBLE_STATUS
