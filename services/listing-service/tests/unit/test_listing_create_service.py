"""ListingCreateService with stub repos."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import NewListing
from app.repositories.seller_repo import SellerEligibility
from app.services.listing_create import (
    BvnRequired,
    CreateListingInput,
    InvalidUrgency,
    ListingCreateService,
    NotSeller,
)
from app.services.poa_guard import PoaNotVerified

_OWNER_VERIFIED = SellerEligibility(
    role="seller",
    seller_authority_type="owner",
    poa_verified_status="not_applicable",
    verified_status="id_verified",
    has_identity_document=True,
)


class _StubSellerRepo:
    def __init__(self, eligibility: SellerEligibility | None = _OWNER_VERIFIED) -> None:
        self._eligibility = eligibility

    async def get_eligibility(self, seller_id: UUID) -> SellerEligibility | None:
        return self._eligibility


class _StubListingRepo:
    def __init__(self) -> None:
        self.created: list[NewListing] = []

    async def create(self, listing: NewListing) -> UUID:
        self.created.append(listing)
        return uuid4()


def _service(
    seller: _StubSellerRepo, listings: _StubListingRepo | None = None
) -> tuple[ListingCreateService, _StubListingRepo]:
    repo = listings or _StubListingRepo()
    return (
        ListingCreateService(sellers=seller, listings=repo),  # type: ignore[arg-type]
        repo,
    )


def _input(**overrides: object) -> CreateListingInput:
    base: dict[str, object] = {
        "title": "3-Bed Apartment",
        "property_type": "residential",
        "description": "Nice place",
        "address_text": "12 Admiralty Way, Lekki",
        "lat": 6.4281,
        "lng": 3.4219,
        "lga": "Eti-Osa",
        "state": "Lagos",
        "size_sqm": Decimal("120.50"),
        "asking_price_kobo": 8_000_000_000,
        "sale_type": "normal",
        "urgency_tag": None,
    }
    base.update(overrides)
    return CreateListingInput(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_happy_normal_sale_pending_review_90_day_expiry() -> None:
    svc, repo = _service(_StubSellerRepo())
    before = datetime.now(UTC)
    result = await svc.create(seller_id=uuid4(), data=_input(sale_type="normal"))

    assert result.status == "pending_review"
    assert len(repo.created) == 1
    row = repo.created[0]
    assert row.urgency_tag is None
    assert row.location_wkt == "SRID=4326;POINT(3.4219 6.4281)"  # POINT(lng lat)
    days = (row.expires_at - before).total_seconds() / 86400
    assert 89.9 < days < 90.1


@pytest.mark.asyncio
async def test_happy_distress_sale_uses_urgency_window() -> None:
    svc, repo = _service(_StubSellerRepo())
    before = datetime.now(UTC)
    result = await svc.create(
        seller_id=uuid4(), data=_input(sale_type="distress", urgency_tag="14_days")
    )
    assert result.status == "pending_review"
    row = repo.created[0]
    assert row.urgency_tag == "14_days"
    days = (row.expires_at - before).total_seconds() / 86400
    assert 13.9 < days < 14.1


@pytest.mark.asyncio
async def test_unknown_seller_not_allowed() -> None:
    svc, repo = _service(_StubSellerRepo(eligibility=None))
    with pytest.raises(NotSeller):
        await svc.create(seller_id=uuid4(), data=_input())
    assert repo.created == []


@pytest.mark.asyncio
async def test_buyer_role_not_allowed() -> None:
    elig = SellerEligibility(
        role="buyer",
        seller_authority_type=None,
        poa_verified_status="not_applicable",
        verified_status="id_verified",
        has_identity_document=True,
    )
    svc, _ = _service(_StubSellerRepo(elig))
    with pytest.raises(NotSeller):
        await svc.create(seller_id=uuid4(), data=_input())


@pytest.mark.asyncio
async def test_unverified_identity_requires_bvn() -> None:
    elig = SellerEligibility(
        role="seller",
        seller_authority_type="owner",
        poa_verified_status="not_applicable",
        verified_status="phone_verified",
        has_identity_document=False,
    )
    svc, repo = _service(_StubSellerRepo(elig))
    with pytest.raises(BvnRequired):
        await svc.create(seller_id=uuid4(), data=_input())
    assert repo.created == []


@pytest.mark.asyncio
async def test_identity_document_alone_satisfies_gate() -> None:
    # verified_status not yet id_verified, but a BVN/NIN hash is on file.
    elig = SellerEligibility(
        role="seller",
        seller_authority_type="owner",
        poa_verified_status="not_applicable",
        verified_status="phone_verified",
        has_identity_document=True,
    )
    svc, repo = _service(_StubSellerRepo(elig))
    result = await svc.create(seller_id=uuid4(), data=_input())
    assert result.status == "pending_review"
    assert len(repo.created) == 1


@pytest.mark.asyncio
async def test_poa_seller_pending_is_blocked() -> None:
    elig = SellerEligibility(
        role="seller",
        seller_authority_type="power_of_attorney",
        poa_verified_status="pending",
        verified_status="id_verified",
        has_identity_document=True,
    )
    svc, repo = _service(_StubSellerRepo(elig))
    with pytest.raises(PoaNotVerified):
        await svc.create(seller_id=uuid4(), data=_input())
    assert repo.created == []


@pytest.mark.asyncio
async def test_poa_seller_verified_can_create() -> None:
    elig = SellerEligibility(
        role="seller",
        seller_authority_type="power_of_attorney",
        poa_verified_status="verified",
        verified_status="id_verified",
        has_identity_document=True,
    )
    svc, repo = _service(_StubSellerRepo(elig))
    result = await svc.create(seller_id=uuid4(), data=_input())
    assert result.status == "pending_review"


@pytest.mark.asyncio
async def test_distress_without_urgency_is_422() -> None:
    svc, repo = _service(_StubSellerRepo())
    with pytest.raises(InvalidUrgency):
        await svc.create(seller_id=uuid4(), data=_input(sale_type="distress", urgency_tag=None))
    assert repo.created == []


@pytest.mark.asyncio
async def test_normal_sale_ignores_urgency_tag() -> None:
    # A stray urgency tag on a normal sale is dropped (DB CHECK needs NULL).
    svc, repo = _service(_StubSellerRepo())
    await svc.create(seller_id=uuid4(), data=_input(sale_type="normal", urgency_tag="7_days"))
    assert repo.created[0].urgency_tag is None
