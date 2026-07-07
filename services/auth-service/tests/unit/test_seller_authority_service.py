"""Unit tests for SellerAuthorityService (SCRUM-132)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.seller_authority import NotSeller, SellerAuthorityService

pytestmark = pytest.mark.asyncio


class _StubUsers:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str]] = []

    async def set_seller_authority(self, user_id: UUID, *, authority_type: str) -> None:
        self.calls.append((user_id, authority_type))


def _service(users: _StubUsers) -> SellerAuthorityService:
    return SellerAuthorityService(users=users)  # type: ignore[arg-type]


@pytest.mark.parametrize("authority", ["owner", "power_of_attorney"])
async def test_seller_can_declare_authority(authority: str) -> None:
    users = _StubUsers()
    uid = uuid4()
    await _service(users).set(user_id=uid, role="seller", authority_type=authority)
    assert users.calls == [(uid, authority)]


@pytest.mark.parametrize("role", ["buyer", "realtor"])
async def test_non_seller_rejected(role: str) -> None:
    users = _StubUsers()
    with pytest.raises(NotSeller):
        await _service(users).set(user_id=uuid4(), role=role, authority_type="owner")
    assert users.calls == []  # nothing written
