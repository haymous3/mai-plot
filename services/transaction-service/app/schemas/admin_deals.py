"""Schemas for the admin deal picker (SCRUM-213)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.transaction_repo import AdminDealRow


class AdminDealItem(BaseModel):
    """One deal an admin can send a realtor to inspect.

    Parties are 8-char references, never names or contacts: §10 masks them from
    everyone but each other, and an admin picking a deal needs the property.
    """

    id: UUID
    listing_id: UUID
    stage: str
    agreed_price_kobo: int
    created_at: datetime
    property_title: str | None
    lga: str | None
    state: str | None
    buyer_ref: str
    seller_ref: str

    @classmethod
    def from_row(cls, row: AdminDealRow) -> AdminDealItem:
        return cls(
            id=row.id,
            listing_id=row.listing_id,
            stage=row.stage,
            agreed_price_kobo=row.agreed_price_kobo,
            created_at=row.created_at,
            property_title=row.property_title,
            lga=row.lga,
            state=row.state,
            buyer_ref=str(row.buyer_id)[:8],
            seller_ref=str(row.seller_id)[:8],
        )


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class AdminDealsResponse(BaseModel):
    items: list[AdminDealItem]
    pagination: Pagination
