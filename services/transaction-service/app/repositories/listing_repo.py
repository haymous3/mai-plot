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


@dataclass(frozen=True)
class PropertySummary:
    """A listing's headline details for the buyer's financing page (SCRUM-94):
    what the property is, where it is, its asking price, and a cover image. The
    image is a public CloudFront URL (media is CDN-served, not presigned)."""

    title: str
    property_type: str
    address_text: str
    lga: str
    state: str
    sale_type: str
    asking_price_kobo: int
    primary_image_url: str | None


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_property_summary(self, listing_id: UUID) -> PropertySummary | None:
        """Headline listing details + a cover image for the financing page. The
        image is the lowest-sorted image in listing_media (a public CDN URL), or
        None if the listing has no photos yet."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT title, property_type, address_text, lga, state, sale_type,
                           asking_price_kobo,
                           (SELECT cdn_url FROM listing_media
                             WHERE listing_id = :id AND media_type = 'image'
                             ORDER BY sort_order LIMIT 1) AS primary_image_url
                    FROM property_listings
                    WHERE id = :id AND deleted_at IS NULL
                    """
                ),
                {"id": listing_id},
            )
        ).first()
        if row is None:
            return None
        return PropertySummary(
            title=row.title,
            property_type=row.property_type,
            address_text=row.address_text,
            lga=row.lga,
            state=row.state,
            sale_type=row.sale_type,
            asking_price_kobo=row.asking_price_kobo,
            primary_image_url=row.primary_image_url,
        )

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
        under_offer). The 72h window is tracked on transactions.lock_expires_at;
        release_lock / mark_sold end the lock (SCRUM-68)."""
        await self._session.execute(
            text(
                "UPDATE property_listings SET status = 'under_offer', updated_at = NOW() "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": listing_id},
        )

    async def release_lock(self, listing_id: UUID) -> None:
        """Reopen a listing whose offer lock has ended (under_offer → active):
        the 72h window lapsed without progress, or the deal was cancelled.
        Guarded on under_offer so a sold/expired listing is never resurrected."""
        await self._session.execute(
            text(
                "UPDATE property_listings SET status = 'active', updated_at = NOW() "
                "WHERE id = :id AND status = 'under_offer' AND deleted_at IS NULL"
            ),
            {"id": listing_id},
        )

    async def mark_sold(self, listing_id: UUID) -> None:
        """Close a listing when its deal completes (→ sold)."""
        await self._session.execute(
            text(
                "UPDATE property_listings SET status = 'sold', updated_at = NOW() "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": listing_id},
        )
