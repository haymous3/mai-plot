"""Cross-service access to property_listings (owned by listing-service).

Same shared-DB pattern used elsewhere (listing-service reads users; document-
service reads property_listings): transaction-service reads a listing's
owner/status to validate offers, and flips it to 'under_offer' when an offer is
accepted. Becomes a REST call when the databases are split.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ListingForOffer:
    seller_id: UUID
    status: str
    expires_at: datetime | None


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_offer(self, listing_id: UUID) -> ListingForOffer | None:
        """Owner + status + expiry of a live listing, for offer validation."""
        row = (
            await self._session.execute(
                text(
                    "SELECT seller_id, status, expires_at FROM property_listings "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": listing_id},
            )
        ).first()
        if row is None:
            return None
        return ListingForOffer(
            seller_id=row.seller_id, status=row.status, expires_at=row.expires_at
        )

    async def mark_under_offer(self, listing_id: UUID) -> None:
        """Lock the listing to other buyers on offer acceptance (status →
        under_offer). The 72h lock window/release is refined in SCRUM-68."""
        await self._session.execute(
            text(
                "UPDATE property_listings SET status = 'under_offer', updated_at = NOW() "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": listing_id},
        )
