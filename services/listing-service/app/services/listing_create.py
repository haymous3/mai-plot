"""Create-listing orchestration (SCRUM-22).

Enforces the publish rules server-side before a row is written:
  * caller must be a seller (role from the shared users table),
  * seller must have a verified identity on file (BVN/NIN) -> else BVN_REQUIRED,
  * a power_of_attorney seller must be PoA-verified -> else POA_NOT_VERIFIED,
  * distress sales require an urgency tag -> else URGENCY_TAG_REQUIRED_FOR_DISTRESS.

New listings start in 'pending_review' (admin approves later) and carry an
expiry: distress auto-expires after its urgency window; normal sales run 90
days (business rules §2/§3).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.repositories.listing_repo import ListingRepository, NewListing
from app.repositories.seller_repo import SellerRepository
from app.services.listing_rules import resolve_urgency_and_expiry
from app.services.poa_guard import ensure_can_publish

# Identity states that count as "ID verified" for the BVN_REQUIRED gate.
_ID_VERIFIED_STATUSES = frozenset({"id_verified", "fully_verified"})


class ListingCreateError(RuntimeError):
    pass


class NotSeller(ListingCreateError):
    """Caller is not a seller (or the account is unknown/inactive)."""


class BvnRequired(ListingCreateError):
    """Seller has not completed identity (BVN/NIN) verification."""


@dataclass(frozen=True)
class CreateListingInput:
    title: str
    property_type: str
    description: str | None
    address_text: str
    lat: float
    lng: float
    lga: str
    state: str
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None


@dataclass(frozen=True)
class CreateListingResult:
    listing_id: UUID
    status: str


class ListingCreateService:
    def __init__(self, *, sellers: SellerRepository, listings: ListingRepository) -> None:
        self._sellers = sellers
        self._listings = listings

    async def create(self, *, seller_id: UUID, data: CreateListingInput) -> CreateListingResult:
        # Authorization gates first: an ineligible caller never gets a row
        # written, regardless of the payload.
        eligibility = await self._sellers.get_eligibility(seller_id)
        if eligibility is None or eligibility.role != "seller":
            raise NotSeller()

        if (
            eligibility.verified_status not in _ID_VERIFIED_STATUSES
            and not eligibility.has_identity_document
        ):
            raise BvnRequired()

        # PoA sellers must be PoA-verified (403 POA_NOT_VERIFIED).
        ensure_can_publish(
            seller_authority_type=eligibility.seller_authority_type,
            poa_verified_status=eligibility.poa_verified_status,
        )

        urgency_tag, expires_at = resolve_urgency_and_expiry(
            sale_type=data.sale_type, urgency_tag=data.urgency_tag
        )

        listing_id = await self._listings.create(
            NewListing(
                seller_id=seller_id,
                property_type=data.property_type,
                title=data.title,
                description=data.description,
                address_text=data.address_text,
                # PostGIS POINT is (x y) = (lng lat).
                location_wkt=f"SRID=4326;POINT({data.lng} {data.lat})",
                lga=data.lga,
                state=data.state,
                size_sqm=data.size_sqm,
                asking_price_kobo=data.asking_price_kobo,
                sale_type=data.sale_type,
                urgency_tag=urgency_tag,
                expires_at=expires_at,
            )
        )
        return CreateListingResult(listing_id=listing_id, status="pending_review")
