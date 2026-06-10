"""ListingUpdateService — ownership, sold-lock, sale_type/urgency conversion."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import OwnerStatus
from app.security import CurrentUser
from app.services.listing_rules import InvalidUrgency
from app.services.listing_update import (
    CannotEditSoldListing,
    ListingNotFound,
    ListingUpdateService,
    NotListingOwner,
)

_OWNER_ID = uuid4()


class _StubRepo:
    def __init__(self, owner: OwnerStatus | None) -> None:
        self._owner = owner
        self.updates: dict[str, object] | None = None
        self.apply_calls = 0

    async def get_owner_status(self, listing_id: UUID) -> OwnerStatus | None:
        return self._owner

    async def apply_update(self, listing_id: UUID, updates: dict[str, object]) -> None:
        self.apply_calls += 1
        self.updates = updates


def _owner_status(*, status: str = "active", sale_type: str = "normal") -> OwnerStatus:
    return OwnerStatus(seller_id=_OWNER_ID, status=status, sale_type=sale_type)


def _service(repo: _StubRepo) -> ListingUpdateService:
    return ListingUpdateService(redis=None, listings=repo)  # type: ignore[arg-type]


def _owner() -> CurrentUser:
    return CurrentUser(user_id=_OWNER_ID, role="seller")


def _days_from_now(when: object) -> float:
    assert isinstance(when, datetime)
    return (when - datetime.now(UTC)).total_seconds() / 86400


@pytest.mark.asyncio
async def test_missing_listing_raises() -> None:
    with pytest.raises(ListingNotFound):
        await _service(_StubRepo(None)).update(
            listing_id=uuid4(), caller=_owner(), changes={"title": "x"}
        )


@pytest.mark.asyncio
async def test_non_owner_rejected() -> None:
    repo = _StubRepo(_owner_status())
    stranger = CurrentUser(user_id=uuid4(), role="seller")
    with pytest.raises(NotListingOwner):
        await _service(repo).update(listing_id=uuid4(), caller=stranger, changes={"title": "x"})
    assert repo.apply_calls == 0


@pytest.mark.asyncio
async def test_admin_can_edit_others_listing() -> None:
    repo = _StubRepo(_owner_status())
    admin = CurrentUser(user_id=uuid4(), role="admin")
    await _service(repo).update(listing_id=uuid4(), caller=admin, changes={"title": "New"})
    assert repo.updates == {"title": "New"}


@pytest.mark.asyncio
async def test_sold_listing_is_frozen() -> None:
    repo = _StubRepo(_owner_status(status="sold"))
    with pytest.raises(CannotEditSoldListing):
        await _service(repo).update(
            listing_id=uuid4(), caller=_owner(), changes={"asking_price_kobo": 1}
        )
    assert repo.apply_calls == 0


@pytest.mark.asyncio
async def test_partial_scalar_update_only_touches_sent_fields() -> None:
    repo = _StubRepo(_owner_status())
    await _service(repo).update(
        listing_id=uuid4(), caller=_owner(), changes={"title": "T", "asking_price_kobo": 999}
    )
    assert repo.updates == {"title": "T", "asking_price_kobo": 999}


@pytest.mark.asyncio
async def test_location_update_builds_wkt() -> None:
    repo = _StubRepo(_owner_status())
    await _service(repo).update(
        listing_id=uuid4(),
        caller=_owner(),
        changes={"location": {"lat": 6.5, "lng": 3.4}},
    )
    assert repo.updates is not None
    assert repo.updates["location"] == "SRID=4326;POINT(3.4 6.5)"


@pytest.mark.asyncio
async def test_convert_normal_to_distress_sets_urgency_and_expiry() -> None:
    repo = _StubRepo(_owner_status(sale_type="normal"))
    await _service(repo).update(
        listing_id=uuid4(),
        caller=_owner(),
        changes={"sale_type": "distress", "urgency_tag": "14_days"},
    )
    assert repo.updates is not None
    assert repo.updates["sale_type"] == "distress"
    assert repo.updates["urgency_tag"] == "14_days"
    assert 13.9 < _days_from_now(repo.updates["expires_at"]) < 14.1


@pytest.mark.asyncio
async def test_convert_to_distress_without_urgency_is_invalid() -> None:
    repo = _StubRepo(_owner_status(sale_type="normal"))
    with pytest.raises(InvalidUrgency):
        await _service(repo).update(
            listing_id=uuid4(), caller=_owner(), changes={"sale_type": "distress"}
        )
    assert repo.apply_calls == 0


@pytest.mark.asyncio
async def test_convert_distress_to_normal_clears_urgency_and_sets_90_days() -> None:
    repo = _StubRepo(_owner_status(sale_type="distress"))
    await _service(repo).update(
        listing_id=uuid4(), caller=_owner(), changes={"sale_type": "normal"}
    )
    assert repo.updates is not None
    assert repo.updates["sale_type"] == "normal"
    assert repo.updates["urgency_tag"] is None
    assert 89.9 < _days_from_now(repo.updates["expires_at"]) < 90.1


@pytest.mark.asyncio
async def test_change_urgency_on_distress_rederives_expiry() -> None:
    repo = _StubRepo(_owner_status(sale_type="distress"))
    await _service(repo).update(
        listing_id=uuid4(), caller=_owner(), changes={"urgency_tag": "30_days"}
    )
    assert repo.updates is not None
    assert repo.updates["urgency_tag"] == "30_days"
    assert 29.9 < _days_from_now(repo.updates["expires_at"]) < 30.1


@pytest.mark.asyncio
async def test_urgency_on_normal_without_conversion_is_ignored() -> None:
    repo = _StubRepo(_owner_status(sale_type="normal"))
    await _service(repo).update(
        listing_id=uuid4(), caller=_owner(), changes={"urgency_tag": "7_days"}
    )
    # Nothing applicable changed -> no urgency/expiry write, apply skipped.
    assert repo.apply_calls == 0


@pytest.mark.asyncio
async def test_empty_changes_skips_apply_but_succeeds() -> None:
    repo = _StubRepo(_owner_status())
    result = await _service(repo).update(listing_id=uuid4(), caller=_owner(), changes={})
    assert repo.apply_calls == 0
    assert result.status == "active"
