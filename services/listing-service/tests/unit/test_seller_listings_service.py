"""Unit tests for SellerListingsService (SCRUM-98)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import OwnerStatus
from app.security import CurrentUser
from app.services.seller_listings import (
    ListingNotFound,
    ListingNotPausable,
    NotListingOwner,
    SellerListingsService,
)

pytestmark = pytest.mark.asyncio

_SELLER = uuid4()


class _StubListings:
    def __init__(self, owner: OwnerStatus | None) -> None:
        self._owner = owner
        self.status_set: list[tuple[UUID, str]] = []

    async def get_owner_status(self, listing_id: UUID) -> OwnerStatus | None:
        return self._owner

    async def set_status(self, listing_id: UUID, *, status: str) -> None:
        self.status_set.append((listing_id, status))


def _caller(uid: UUID = _SELLER) -> CurrentUser:
    return CurrentUser(user_id=uid, role="seller")


def _owner(status: str, seller: UUID = _SELLER) -> OwnerStatus:
    return OwnerStatus(seller_id=seller, status=status, sale_type="normal")


async def test_pause_active_listing() -> None:
    repo = _StubListings(_owner("active"))
    await SellerListingsService(listings=repo).pause(listing_id=uuid4(), caller=_caller())  # type: ignore[arg-type]
    assert repo.status_set[0][1] == "paused"


async def test_resume_paused_listing() -> None:
    repo = _StubListings(_owner("paused"))
    await SellerListingsService(listings=repo).resume(listing_id=uuid4(), caller=_caller())  # type: ignore[arg-type]
    assert repo.status_set[0][1] == "active"


async def test_pause_unknown_listing_raises() -> None:
    repo = _StubListings(None)
    with pytest.raises(ListingNotFound):
        await SellerListingsService(listings=repo).pause(listing_id=uuid4(), caller=_caller())  # type: ignore[arg-type]


async def test_pause_non_owner_raises() -> None:
    repo = _StubListings(_owner("active", seller=uuid4()))
    with pytest.raises(NotListingOwner):
        await SellerListingsService(listings=repo).pause(listing_id=uuid4(), caller=_caller())  # type: ignore[arg-type]


async def test_pause_non_active_raises() -> None:
    repo = _StubListings(_owner("under_offer"))
    with pytest.raises(ListingNotPausable):
        await SellerListingsService(listings=repo).pause(listing_id=uuid4(), caller=_caller())  # type: ignore[arg-type]
    assert repo.status_set == []
