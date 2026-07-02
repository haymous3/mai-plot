"""Integration tests for GET /loans/bank-partners (SCRUM-94)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_lists_active_partners_sorted_excludes_inactive(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seed_bank_partner(name="GTBank")
    seed_bank_partner(name="Access Bank")
    seed_bank_partner(name="Dormant Bank", is_active=False)

    resp = await http_client.get(
        "/loans/bank-partners", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    names = [i["name"] for i in items]
    assert names == ["Access Bank", "GTBank"]  # sorted, inactive excluded
    first = items[0]
    assert first["interest_rate_bps"] == 2200
    assert first["min_tenure_months"] == 6
    assert first["max_tenure_months"] == 36
    assert first["loan_max_kobo"] == 500_000_000
    assert first["requires_account_opening"] is True  # column default


async def test_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/loans/bank-partners")
    assert resp.status_code == 401
