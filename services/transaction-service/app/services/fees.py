"""Platform fee calculation (SCRUM-119).

A pure function so the kobo arithmetic is trivially testable. Kept distinct from
the realtor commission (CLAUDE.md rule §7, a separate 2%): this is Maiplot's own
platform fee, carved out of the seller's proceeds at deal close.
"""

from __future__ import annotations

# 10_000 basis points = 100%.
_BPS_DENOMINATOR = 10_000


def compute_platform_fee_kobo(agreed_price_kobo: int, fee_bps: int) -> int:
    """The platform fee on a closed deal, in whole kobo.

    floor(agreed_price_kobo * fee_bps / 10_000). Integer math throughout (money
    is BIGINT kobo, never float) and rounded DOWN, so the platform never charges
    a fraction of a kobo more than the exact rate — any rounding favours the
    seller.
    """
    if agreed_price_kobo < 0 or fee_bps < 0:
        raise ValueError("agreed_price_kobo and fee_bps must be non-negative")
    return agreed_price_kobo * fee_bps // _BPS_DENOMINATOR
