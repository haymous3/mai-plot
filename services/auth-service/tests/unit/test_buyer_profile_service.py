"""Unit tests for BuyerProfileService (SCRUM-132)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.buyer_profile import BuyerProfileService, NotBuyer

pytestmark = pytest.mark.asyncio


class _StubProfiles:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def upsert(
        self,
        user_id: UUID,
        *,
        employment_status: str | None,
        preferred_location: str | None,
        budget_kobo: int | None,
    ) -> None:
        self.calls.append(
            {
                "user_id": user_id,
                "employment_status": employment_status,
                "preferred_location": preferred_location,
                "budget_kobo": budget_kobo,
            }
        )


def _service(profiles: _StubProfiles) -> BuyerProfileService:
    return BuyerProfileService(profiles=profiles)  # type: ignore[arg-type]


async def test_buyer_profile_saved() -> None:
    profiles = _StubProfiles()
    uid = uuid4()
    await _service(profiles).save(
        user_id=uid,
        role="buyer",
        employment_status="employed",
        preferred_location="  Lagos  ",
        budget_kobo=4_000_000_000,
    )
    assert profiles.calls == [
        {
            "user_id": uid,
            "employment_status": "employed",
            "preferred_location": "Lagos",  # trimmed
            "budget_kobo": 4_000_000_000,
        }
    ]


async def test_blank_location_becomes_none() -> None:
    profiles = _StubProfiles()
    await _service(profiles).save(
        user_id=uuid4(),
        role="buyer",
        employment_status=None,
        preferred_location="   ",
        budget_kobo=None,
    )
    assert profiles.calls[0]["preferred_location"] is None


@pytest.mark.parametrize("role", ["seller", "realtor"])
async def test_non_buyer_rejected(role: str) -> None:
    profiles = _StubProfiles()
    with pytest.raises(NotBuyer):
        await _service(profiles).save(
            user_id=uuid4(),
            role=role,
            employment_status="employed",
            preferred_location=None,
            budget_kobo=None,
        )
    assert profiles.calls == []
