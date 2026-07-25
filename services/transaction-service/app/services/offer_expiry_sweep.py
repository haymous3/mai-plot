"""Proactive sweep of lapsed offers (SCRUM-118).

An offer auto-expires 72h after it's made if the seller never responds (rule §4).
OfferService enforces this LAZILY — it refuses a stale offer on read/respond but
never mutates the row, so a pending offer that no one touches again lingers in
'pending' forever (and shows as active in the buyer's/seller's lists). This beat
sweep is the proactive counterpart: it stamps status='expired' on every
pending/countered offer past its window, so the lists reflect reality.

Idempotent + re-entrant: the repo query only returns still-live offers, so an
offer expired on one pass is gone the next.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.repositories.offer_repo import OfferRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OfferExpiryResult:
    expired: int


class OfferExpirySweepService:
    def __init__(self, *, offers: OfferRepository, batch_limit: int = 500) -> None:
        self._offers = offers
        self._batch_limit = batch_limit

    async def run(self) -> OfferExpiryResult:
        expired = await self._offers.expire_lapsed(limit=self._batch_limit)
        if expired:
            logger.info("offer.expiry_sweep.expired", extra={"count": expired})
        return OfferExpiryResult(expired=expired)
