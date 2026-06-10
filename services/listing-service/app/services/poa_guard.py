"""PoA publish guard (business rule §1).

A seller whose authority_type is `power_of_attorney` cannot publish ANY
listing until their PoA document is verified by the legal team. This is the
same pure rule auth-service exposes (app.services.poa_guard there); it is
re-implemented here rather than imported because each service owns its own
`app` package and there is no shared library member yet. If a `_shared`
workspace package is introduced later, both copies collapse into it.
"""

from __future__ import annotations


class PoaNotVerified(Exception):
    """A PoA seller whose PoA is not yet verified — publication is refused
    with 403 POA_NOT_VERIFIED."""


def ensure_can_publish(*, seller_authority_type: str | None, poa_verified_status: str) -> None:
    """Raise PoaNotVerified if a PoA seller has not been PoA-verified.

    Owners and non-sellers are unaffected — only power_of_attorney sellers
    are gated, and only until poa_verified_status reaches 'verified'.
    """
    if seller_authority_type == "power_of_attorney" and poa_verified_status != "verified":
        raise PoaNotVerified()
