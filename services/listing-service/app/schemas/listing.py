"""Request/response models for the /listings endpoints.

Field shapes mirror api-contracts.md §Listing Service. The urgency-tag rule
(required for distress, forbidden for normal) is enforced in the service so
it can return the specific 422 URGENCY_TAG_REQUIRED_FOR_DISTRESS code rather
than a generic Pydantic validation error.
"""

from __future__ import annotations

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


class ErrorResponse(BaseModel):
    """Matches the standard error envelope in api-contracts.md."""

    error_code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
