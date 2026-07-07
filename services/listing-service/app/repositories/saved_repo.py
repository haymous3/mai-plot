"""DB access for saved_listings (SCRUM-95).

Repository layer per CLAUDE.md §4. Save/unsave is a soft-delete toggle keyed on
(buyer_id, listing_id); the saved feed joins property_listings so the Saved
Properties card renders the same card shape as the main feed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.listing_repo import FeedRow


class SavedListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, *, buyer_id: UUID, listing_id: UUID) -> None:
        """Idempotent save — a re-save of a previously unsaved listing clears
        deleted_at rather than inserting a duplicate (UNIQUE(buyer_id, listing_id))."""
        await self._session.execute(
            text(
                """
                INSERT INTO saved_listings (buyer_id, listing_id)
                VALUES (:buyer_id, :listing_id)
                ON CONFLICT (buyer_id, listing_id)
                DO UPDATE SET deleted_at = NULL, updated_at = NOW()
                """
            ),
            {"buyer_id": buyer_id, "listing_id": listing_id},
        )

    async def unsave(self, *, buyer_id: UUID, listing_id: UUID) -> None:
        await self._session.execute(
            text(
                """
                UPDATE saved_listings SET deleted_at = NOW(), updated_at = NOW()
                WHERE buyer_id = :buyer_id AND listing_id = :listing_id
                  AND deleted_at IS NULL
                """
            ),
            {"buyer_id": buyer_id, "listing_id": listing_id},
        )

    async def list_saved_ids(self, buyer_id: UUID) -> set[UUID]:
        rows = (
            await self._session.execute(
                text(
                    "SELECT listing_id FROM saved_listings "
                    "WHERE buyer_id = :buyer_id AND deleted_at IS NULL"
                ),
                {"buyer_id": buyer_id},
            )
        ).all()
        return {r.listing_id for r in rows}

    async def list_saved_feed(self, buyer_id: UUID) -> list[FeedRow]:
        """The buyer's saved (still-active) listings as feed cards, newest-saved
        first. Mirrors listing_repo.list_feed's projection."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT pl.id, pl.title, pl.property_type, pl.state, pl.lga, pl.size_sqm,
                           pl.asking_price_kobo, pl.sale_type, pl.urgency_tag, pl.expires_at,
                           pl.status, pl.doc_verification_status, pl.view_count,
                           pl.interest_count, pl.created_at, u.seller_authority_type
                    FROM saved_listings s
                    JOIN property_listings pl ON pl.id = s.listing_id
                    LEFT JOIN users u ON u.id = pl.seller_id
                    WHERE s.buyer_id = :buyer_id AND s.deleted_at IS NULL
                      AND pl.deleted_at IS NULL AND pl.status = 'active'
                    ORDER BY s.created_at DESC
                    """
                ),
                {"buyer_id": buyer_id},
            )
        ).all()
        return [
            FeedRow(
                id=r.id,
                title=r.title,
                property_type=r.property_type,
                state=r.state,
                lga=r.lga,
                size_sqm=r.size_sqm,
                asking_price_kobo=r.asking_price_kobo,
                sale_type=r.sale_type,
                urgency_tag=r.urgency_tag,
                expires_at=r.expires_at,
                status=r.status,
                doc_verification_status=r.doc_verification_status,
                view_count=r.view_count,
                interest_count=r.interest_count,
                created_at=r.created_at,
                seller_authority_type=r.seller_authority_type,
            )
            for r in rows
        ]
