"""Cross-service read of listing ownership from the shared listing table.

The listing's owner lives in listing-service's `property_listings`. To verify
that the uploader owns the listing, document-service reads it directly — the
database is shared (consistent with listing-service reading auth's `users`).
A deliberate trade against CLAUDE.md §3 that holds while services share one
DB; it becomes a REST call to listing-service once databases split. Read-only
via text() to make the cross-service ownership explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ListingOwner:
    seller_id: UUID
    status: str


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_listing_owner(self, listing_id: UUID) -> ListingOwner | None:
        """Owner + status for a live listing, or None if unknown/soft-deleted."""
        row = (
            await self._session.execute(
                text(
                    "SELECT seller_id, status FROM property_listings "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": listing_id},
            )
        ).first()
        if row is None:
            return None
        return ListingOwner(seller_id=row.seller_id, status=row.status)

    async def has_active_offer(self, *, listing_id: UUID, buyer_id: UUID) -> bool:
        """True if this buyer has an engaged (not rejected/withdrawn) offer on
        the listing — the access relationship that lets a buyer view its
        documents during due diligence."""
        exists = (
            await self._session.execute(
                text(
                    """
                    SELECT 1 FROM offers
                    WHERE listing_id = :lid AND buyer_id = :uid
                      AND status IN ('pending', 'accepted', 'countered')
                    LIMIT 1
                    """
                ),
                {"lid": listing_id, "uid": buyer_id},
            )
        ).first()
        return exists is not None
