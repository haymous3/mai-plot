"""Access to the offers table.

The `offers` table is OWNED by listing-service (created in its migration 0001;
also read by document-service's has_active_offer check). transaction-service
reads/writes it via the shared-DB pattern — it does not own or migrate it. The
table has no seller_id, so reads join property_listings to surface it for the
seller authorization checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class OfferRow:
    id: UUID
    listing_id: UUID
    buyer_id: UUID
    seller_id: UUID  # joined from property_listings (offers has no seller_id)
    offered_price_kobo: int
    counter_price_kobo: int | None
    status: str
    expires_at: datetime


@dataclass(frozen=True)
class SellerOfferRow:
    """An offer on one of the seller's listings, for the Offers inbox (SCRUM-98).
    Joins property_listings for the title/asking price."""

    id: UUID
    listing_id: UUID
    buyer_id: UUID
    property_title: str
    lga: str
    state: str
    asking_price_kobo: int
    offered_price_kobo: int
    counter_price_kobo: int | None
    note: str | None
    status: str
    created_at: datetime


@dataclass(frozen=True)
class BuyerOfferRow:
    """An offer the buyer placed, for their "Active Offers" list (SCRUM-134).
    Joins property_listings for the title/asking price."""

    id: UUID
    listing_id: UUID
    property_title: str
    lga: str
    state: str
    asking_price_kobo: int
    offered_price_kobo: int
    counter_price_kobo: int | None
    note: str | None
    status: str
    created_at: datetime


class OfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        listing_id: UUID,
        buyer_id: UUID,
        offered_price_kobo: int,
        expires_at: datetime,
    ) -> UUID:
        offer_id = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO offers (listing_id, buyer_id, offered_price_kobo, expires_at)
                    VALUES (:lid, :bid, :price, :exp)
                    RETURNING id
                    """
                ),
                {
                    "lid": listing_id,
                    "bid": buyer_id,
                    "price": offered_price_kobo,
                    "exp": expires_at,
                },
            )
        ).scalar_one()
        assert isinstance(offer_id, UUID)
        return offer_id

    async def get(self, offer_id: UUID) -> OfferRow | None:
        """The offer joined with its listing's seller_id (for authz)."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT o.id, o.listing_id, o.buyer_id, pl.seller_id,
                           o.offered_price_kobo, o.counter_price_kobo, o.status, o.expires_at
                    FROM offers o
                    JOIN property_listings pl ON pl.id = o.listing_id
                    WHERE o.id = :id
                    """
                ),
                {"id": offer_id},
            )
        ).first()
        if row is None:
            return None
        return OfferRow(
            id=row.id,
            listing_id=row.listing_id,
            buyer_id=row.buyer_id,
            seller_id=row.seller_id,
            offered_price_kobo=row.offered_price_kobo,
            counter_price_kobo=row.counter_price_kobo,
            status=row.status,
            expires_at=row.expires_at,
        )

    async def list_for_seller(self, seller_id: UUID) -> list[SellerOfferRow]:
        """Every offer on the seller's listings, newest first."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT o.id, o.listing_id, o.buyer_id, pl.title AS property_title,
                           pl.lga, pl.state, pl.asking_price_kobo, o.offered_price_kobo,
                           o.counter_price_kobo, o.note, o.status, o.created_at
                    FROM offers o
                    JOIN property_listings pl ON pl.id = o.listing_id
                    WHERE pl.seller_id = :sid
                    ORDER BY o.created_at DESC
                    """
                ),
                {"sid": seller_id},
            )
        ).all()
        return [
            SellerOfferRow(
                id=r.id,
                listing_id=r.listing_id,
                buyer_id=r.buyer_id,
                property_title=r.property_title,
                lga=r.lga,
                state=r.state,
                asking_price_kobo=r.asking_price_kobo,
                offered_price_kobo=r.offered_price_kobo,
                counter_price_kobo=r.counter_price_kobo,
                note=r.note,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def list_for_buyer(self, buyer_id: UUID) -> list[BuyerOfferRow]:
        """Every offer the buyer placed, newest first."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT o.id, o.listing_id, pl.title AS property_title, pl.lga, pl.state,
                           pl.asking_price_kobo, o.offered_price_kobo, o.counter_price_kobo,
                           o.note, o.status, o.created_at
                    FROM offers o
                    JOIN property_listings pl ON pl.id = o.listing_id
                    WHERE o.buyer_id = :bid
                    ORDER BY o.created_at DESC
                    """
                ),
                {"bid": buyer_id},
            )
        ).all()
        return [
            BuyerOfferRow(
                id=r.id,
                listing_id=r.listing_id,
                property_title=r.property_title,
                lga=r.lga,
                state=r.state,
                asking_price_kobo=r.asking_price_kobo,
                offered_price_kobo=r.offered_price_kobo,
                counter_price_kobo=r.counter_price_kobo,
                note=r.note,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def expire_lapsed(self, *, limit: int = 500) -> int:
        """Stamp status='expired' on pending/countered offers whose 72h window has
        passed (SCRUM-118) — the proactive counterpart to OfferService's lazy
        expiry. Bulk, batched, idempotent: only still-live offers match, so a
        re-run never re-touches one. Returns how many were expired."""
        rows = (
            await self._session.execute(
                text(
                    """
                    WITH lapsed AS (
                        SELECT id FROM offers
                        WHERE status IN ('pending','countered') AND expires_at <= NOW()
                        ORDER BY expires_at
                        LIMIT :limit
                    )
                    UPDATE offers SET status = 'expired', updated_at = NOW()
                    WHERE id IN (SELECT id FROM lapsed)
                    RETURNING id
                    """
                ),
                {"limit": limit},
            )
        ).all()
        return len(rows)

    async def set_status(self, offer_id: UUID, *, status: str) -> None:
        await self._session.execute(
            text("UPDATE offers SET status = :s, updated_at = NOW() WHERE id = :id"),
            {"s": status, "id": offer_id},
        )

    async def set_countered(self, offer_id: UUID, *, counter_price_kobo: int) -> None:
        await self._session.execute(
            text(
                "UPDATE offers SET status = 'countered', counter_price_kobo = :c, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"c": counter_price_kobo, "id": offer_id},
        )

    async def set_accepted(self, offer_id: UUID) -> None:
        await self._session.execute(
            text("UPDATE offers SET status = 'accepted', updated_at = NOW() WHERE id = :id"),
            {"id": offer_id},
        )
