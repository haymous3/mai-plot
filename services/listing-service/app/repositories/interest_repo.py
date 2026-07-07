"""DB access for listing_interests (SCRUM-95).

A buyer's "Express Interest". Idempotent on (buyer_id, listing_id); the listing's
interest_count is bumped only when a NEW interest row is created.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InterestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def express(self, *, buyer_id: UUID, listing_id: UUID, message: str | None) -> bool:
        """Record interest. Returns True if this was the buyer's first interest
        in the listing (in which case interest_count was incremented), False if
        they had already expressed interest."""
        inserted = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO listing_interests (buyer_id, listing_id, message)
                    VALUES (:buyer_id, :listing_id, :message)
                    ON CONFLICT (buyer_id, listing_id) DO NOTHING
                    RETURNING id
                    """
                ),
                {"buyer_id": buyer_id, "listing_id": listing_id, "message": message},
            )
        ).first()
        if inserted is None:
            return False
        await self._session.execute(
            text(
                "UPDATE property_listings SET interest_count = interest_count + 1 "
                "WHERE id = :listing_id"
            ),
            {"listing_id": listing_id},
        )
        return True
