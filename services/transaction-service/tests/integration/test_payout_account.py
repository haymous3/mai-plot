"""Integration tests for payout-account management (SCRUM-145).

paystack_enabled is false in tests, so the fake recipient client mints a
synthetic recipient_code without touching the network.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_VALID = {"account_number": "0123456789", "bank_code": "058", "account_name": "Ada Adeyemo"}


async def test_set_then_get_payout_account(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    headers = auth_header(mint_token(realtor, "realtor"))

    put = await http_client.put("/payout-account", json=_VALID, headers=headers)
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["account_number_masked"] == "••••6789"
    assert body["bank_code"] == "058"
    assert body["account_name"] == "Ada Adeyemo"
    assert body["recipient_ready"] is True
    # The full account number is never returned (financial PII).
    assert "0123456789" not in put.text

    get = await http_client.get("/payout-account", headers=headers)
    assert get.status_code == 200, get.text
    assert get.json()["account_number_masked"] == "••••6789"


async def test_put_replaces_existing_account(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    headers = auth_header(mint_token(seller, "seller"))

    await http_client.put("/payout-account", json=_VALID, headers=headers)
    updated = {"account_number": "9876543210", "bank_code": "011", "account_name": "Ada A"}
    put = await http_client.put("/payout-account", json=updated, headers=headers)
    assert put.status_code == 200, put.text
    assert put.json()["account_number_masked"] == "••••3210"

    get = await http_client.get("/payout-account", headers=headers)
    assert get.json()["bank_code"] == "011"


async def test_get_missing_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    resp = await http_client.get(
        "/payout-account", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "PAYOUT_ACCOUNT_NOT_FOUND"


async def test_invalid_account_number_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    resp = await http_client.put(
        "/payout-account",
        json={"account_number": "12", "bank_code": "058", "account_name": "Ada"},
        headers=auth_header(mint_token(realtor, "realtor")),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


async def test_payout_account_requires_auth(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.get("/payout-account")
    assert resp.status_code == 401
