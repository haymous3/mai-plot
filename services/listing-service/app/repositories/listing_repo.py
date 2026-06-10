"""DB writes for property_listings.

Repository layer per CLAUDE.md §4 — the service layer calls this, route
handlers never touch SQLAlchemy directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PropertyListing


@dataclass(frozen=True)
class NewListing:
    """The fields a create needs. location is a PostGIS WKT string
    (SRID=4326;POINT(lng lat)); the service builds it from lat/lng."""

    seller_id: UUID
    property_type: str
    title: str
    description: str | None
    address_text: str
    location_wkt: str
    lga: str
    state: str
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    expires_at: datetime


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, listing: NewListing) -> UUID:
        """Insert a listing with status 'pending_review' (the DB default) and
        return its id. The caller's get_session dependency commits."""
        row = PropertyListing(
            seller_id=listing.seller_id,
            property_type=listing.property_type,
            title=listing.title,
            description=listing.description,
            address_text=listing.address_text,
            location=listing.location_wkt,
            lga=listing.lga,
            state=listing.state,
            size_sqm=listing.size_sqm,
            asking_price_kobo=listing.asking_price_kobo,
            sale_type=listing.sale_type,
            urgency_tag=listing.urgency_tag,
            status="pending_review",
            expires_at=listing.expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row.id
