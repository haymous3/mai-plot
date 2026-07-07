"""ListingDetailService — loan eligibility, seller block, 404 (redis=None)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import DetailRow, MediaRow
from app.repositories.seller_repo import SellerPublic
from app.security import CurrentUser
from app.services.listing_detail import ListingDetailService

_SELLER_ID = uuid4()


def _detail_row() -> DetailRow:
    return DetailRow(
        id=uuid4(),
        seller_id=_SELLER_ID,
        title="3-Bed Apartment",
        property_type="residential",
        description="Nice",
        address_text="12 Admiralty Way",
        lat=6.4281,
        lng=3.4219,
        size_sqm=Decimal("120.50"),
        asking_price_kobo=8_000_000_000,
        sale_type="distress",
        urgency_tag="7_days",
        expires_at=datetime(2026, 6, 20, tzinfo=UTC),
        status="active",
        view_count=10,
        interest_count=2,
    )


class _StubListingRepo:
    def __init__(self, detail: DetailRow | None, media: list[MediaRow] | None = None) -> None:
        self._detail = detail
        self._media = media or []

    async def get_detail(self, listing_id: UUID) -> DetailRow | None:
        return self._detail

    async def list_media(self, listing_id: UUID) -> list[MediaRow]:
        return self._media


class _StubSellerRepo:
    def __init__(self, seller: SellerPublic | None) -> None:
        self._seller = seller

    async def get_seller_public(self, seller_id: UUID) -> SellerPublic | None:
        return self._seller


class _StubViewCounter:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []

    async def enqueue(self, listing_id: UUID) -> None:
        self.enqueued.append(listing_id)


def _service(
    detail: DetailRow | None,
    *,
    media: list[MediaRow] | None = None,
    seller: SellerPublic | None = SellerPublic(authority_type="owner", poa_owner_name=None),
    view_counter: _StubViewCounter | None = None,
) -> ListingDetailService:
    return ListingDetailService(
        redis=None,
        listings=_StubListingRepo(detail, media),  # type: ignore[arg-type]
        sellers=_StubSellerRepo(seller),  # type: ignore[arg-type]
        ttl_seconds=300,
        view_counter=view_counter,
    )


@pytest.mark.asyncio
async def test_missing_listing_returns_none() -> None:
    result = await _service(None).get_detail(listing_id=uuid4(), viewer=None)
    assert result is None


@pytest.mark.asyncio
async def test_successful_view_dispatches_view_count() -> None:
    counter = _StubViewCounter()
    lid = uuid4()
    await _service(_detail_row(), view_counter=counter).get_detail(listing_id=lid, viewer=None)
    assert counter.enqueued == [lid]


@pytest.mark.asyncio
async def test_missing_listing_does_not_dispatch_view_count() -> None:
    counter = _StubViewCounter()
    await _service(None, view_counter=counter).get_detail(listing_id=uuid4(), viewer=None)
    assert counter.enqueued == []


@pytest.mark.asyncio
async def test_buyer_sees_loan_eligibility_at_50_percent() -> None:
    viewer = CurrentUser(user_id=uuid4(), role="buyer")
    result = await _service(_detail_row()).get_detail(listing_id=uuid4(), viewer=viewer)
    assert result is not None
    assert result.loan_eligibility_kobo == 4_000_000_000  # 50% of 8,000,000,000


@pytest.mark.asyncio
async def test_anonymous_viewer_gets_no_loan_eligibility() -> None:
    result = await _service(_detail_row()).get_detail(listing_id=uuid4(), viewer=None)
    assert result is not None
    assert result.loan_eligibility_kobo is None


@pytest.mark.asyncio
async def test_seller_viewer_gets_no_loan_eligibility() -> None:
    viewer = CurrentUser(user_id=uuid4(), role="seller")
    result = await _service(_detail_row()).get_detail(listing_id=uuid4(), viewer=viewer)
    assert result is not None
    assert result.loan_eligibility_kobo is None


@pytest.mark.asyncio
async def test_detail_shapes_seller_block_and_media_and_location() -> None:
    media = [MediaRow(media_type="photo", cdn_url="https://cdn/x.jpg", sort_order=0)]
    seller = SellerPublic(authority_type="power_of_attorney", poa_owner_name="John Doe")
    result = await _service(_detail_row(), media=media, seller=seller).get_detail(
        listing_id=uuid4(), viewer=None
    )
    assert result is not None
    assert result.seller.id == _SELLER_ID
    assert result.seller.authority_type == "power_of_attorney"
    assert result.seller.poa_owner_name == "John Doe"
    assert result.location.lat == 6.4281
    assert result.location.lng == 3.4219
    assert len(result.media) == 1
    assert result.media[0].type == "photo"
    assert result.media[0].url == "https://cdn/x.jpg"
