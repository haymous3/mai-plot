"""PoA publish guard (business rule §1)."""

from __future__ import annotations

import pytest

from app.services.poa_guard import PoaNotVerified, ensure_can_publish


def test_owner_seller_can_publish() -> None:
    ensure_can_publish(seller_authority_type="owner", poa_verified_status="not_applicable")


def test_non_seller_unaffected() -> None:
    ensure_can_publish(seller_authority_type=None, poa_verified_status="not_applicable")


def test_verified_poa_seller_can_publish() -> None:
    ensure_can_publish(seller_authority_type="power_of_attorney", poa_verified_status="verified")


@pytest.mark.parametrize("status", ["not_applicable", "pending", "rejected"])
def test_unverified_poa_seller_is_blocked(status: str) -> None:
    with pytest.raises(PoaNotVerified):
        ensure_can_publish(seller_authority_type="power_of_attorney", poa_verified_status=status)
