"""DB access for offers (transaction-service's own table)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Offer


@dataclass(frozen=True)
class OfferRow:
    id: UUID
    listing_id: UUID
    buyer_id: UUID
    seller_id: UUID
    amount_kobo: int
    counter_amount_kobo: int | None
    status: str
    transaction_id: UUID | None
    expires_at: datetime


class OfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        listing_id: UUID,
        buyer_id: UUID,
        seller_id: UUID,
        amount_kobo: int,
        expires_at: datetime,
    ) -> UUID:
        offer = Offer(
            listing_id=listing_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount_kobo=amount_kobo,
            expires_at=expires_at,
            status="pending",
        )
        self._session.add(offer)
        await self._session.flush()
        return offer.id

    async def get(self, offer_id: UUID) -> OfferRow | None:
        stmt = select(Offer).where(Offer.id == offer_id, Offer.deleted_at.is_(None))
        offer = (await self._session.execute(stmt)).scalar_one_or_none()
        if offer is None:
            return None
        return OfferRow(
            id=offer.id,
            listing_id=offer.listing_id,
            buyer_id=offer.buyer_id,
            seller_id=offer.seller_id,
            amount_kobo=offer.amount_kobo,
            counter_amount_kobo=offer.counter_amount_kobo,
            status=offer.status,
            transaction_id=offer.transaction_id,
            expires_at=offer.expires_at,
        )

    async def set_status(self, offer_id: UUID, *, status: str) -> None:
        offer = await self._session.get(Offer, offer_id)
        if offer is not None:
            offer.status = status
            offer.updated_at = datetime.now(UTC)

    async def set_countered(self, offer_id: UUID, *, counter_amount_kobo: int) -> None:
        offer = await self._session.get(Offer, offer_id)
        if offer is not None:
            offer.status = "countered"
            offer.counter_amount_kobo = counter_amount_kobo
            offer.updated_at = datetime.now(UTC)

    async def set_accepted(self, offer_id: UUID, *, transaction_id: UUID) -> None:
        offer = await self._session.get(Offer, offer_id)
        if offer is not None:
            offer.status = "accepted"
            offer.transaction_id = transaction_id
            offer.updated_at = datetime.now(UTC)
