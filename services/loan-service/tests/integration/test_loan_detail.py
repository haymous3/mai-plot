"""Integration tests for GET /loans/{loan_id} (SCRUM-94)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_buyer_sees_own_loan_detail_with_bank_name(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner(name="GTBank")
    loan = seed_loan(
        buyer_id=buyer,
        tx_id=tx,
        partner_id=partner,
        reference="REF-DETAIL",
        status="approved",
        approved_amount_kobo=30_000_000,
    )

    resp = await http_client.get(f"/loans/{loan}", headers=auth_header(mint_token(buyer, "buyer")))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["loan_id"] == str(loan)
    assert body["status"] == "approved"
    assert body["approved_amount_kobo"] == 30_000_000
    assert body["bank_name"] == "GTBank"
    assert body["requires_account_opening"] is True
    assert body["title_released"] is False


async def test_stranger_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    loan = seed_loan(buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-DETAIL2")

    stranger = seed_user(role="buyer")
    resp = await http_client.get(
        f"/loans/{loan}", headers=auth_header(mint_token(stranger, "buyer"))
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_LOAN_VIEWER"


async def test_unknown_loan_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    resp = await http_client.get(
        f"/loans/{uuid4()}", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "LOAN_NOT_FOUND"
