"""Reusable PoA publish guard (business rule §1, SCRUM-48).

A seller whose authority_type is `power_of_attorney` cannot publish ANY
listing until their PoA document is verified by the legal team. This pure
function encodes that rule once; listing-service imports it at its
`POST /listings` handler when that service is built. Keeping it free of DB
and HTTP concerns lets both services share the exact same check.
"""

from __future__ import annotations


class PoaNotVerified(Exception):
    """The caller is a PoA seller whose PoA is not yet verified — listing
    publication must be refused with 403 POA_NOT_VERIFIED."""


def ensure_can_publish(*, seller_authority_type: str | None, poa_verified_status: str) -> None:
    """Raise PoaNotVerified if a PoA seller has not been PoA-verified.

    Owners (and non-sellers) are unaffected — only power_of_attorney sellers
    are gated, and only until poa_verified_status reaches 'verified'.
    """
    if seller_authority_type == "power_of_attorney" and poa_verified_status != "verified":
        raise PoaNotVerified()
