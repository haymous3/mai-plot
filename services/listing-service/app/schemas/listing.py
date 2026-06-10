"""Request/response models for the /listings endpoints.

Field shapes mirror api-contracts.md §Listing Service. The urgency-tag rule
(required for distress, forbidden for normal) is enforced in the service so
it can return the specific 422 URGENCY_TAG_REQUIRED_FOR_DISTRESS code rather
than a generic Pydantic validation error.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PropertyType = Literal["land", "residential", "commercial"]
SaleType = Literal["distress", "normal"]
UrgencyTag = Literal["7_days", "14_days", "30_days"]


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class CreateListingRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=300)
    property_type: PropertyType
    description: str | None = Field(default=None, max_length=10_000)
    address_text: str = Field(min_length=1)
    location: GeoPoint
    lga: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=50)
    size_sqm: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    asking_price_kobo: int = Field(gt=0)
    sale_type: SaleType
    # urgency_tag is accepted but cross-validated against sale_type in the
    # service (distress requires it; normal must omit it).
    urgency_tag: UrgencyTag | None = None


class CreateListingResponse(BaseModel):
    listing_id: UUID
    status: str = "pending_review"


# ---- Feed (GET /listings) -------------------------------------------------

SortOption = Literal["urgency", "recency", "price_asc", "price_desc"]


class FeedItem(BaseModel):
    id: UUID
    title: str
    property_type: str
    state: str
    lga: str
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    urgency_expires_at: datetime | None
    status: str
    doc_verification_status: str
    thumbnail_url: str | None
    seller_authority_type: str | None
    view_count: int
    interest_count: int
    created_at: datetime


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class FeedResponse(BaseModel):
    data: list[FeedItem]
    pagination: Pagination


# ---- Detail (GET /listings/{id}) ------------------------------------------


class SellerBlock(BaseModel):
    id: UUID
    authority_type: str | None
    poa_owner_name: str | None = None
    # trust_score is sourced from analytics (not yet built) — null for now.
    trust_score: float | None = None


class MediaItem(BaseModel):
    type: str
    url: str
    sort_order: int


class ListingDetailResponse(BaseModel):
    id: UUID
    seller: SellerBlock
    title: str
    description: str | None
    address_text: str
    location: GeoPoint
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    urgency_expires_at: datetime | None
    status: str
    media: list[MediaItem]
    # 50% of asking price for an authenticated buyer; null otherwise.
    loan_eligibility_kobo: int | None
    view_count: int
    interest_count: int


class ErrorResponse(BaseModel):
    """Matches the standard error envelope in api-contracts.md."""

    error_code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
