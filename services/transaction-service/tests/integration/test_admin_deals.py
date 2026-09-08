"""GET /admin/transactions integration tests (SCRUM-213).

The deal picker behind manual inspection assignment. Nothing listed deals for an
admin before this: `/admin/escrow/{transaction_id}` needs an id you already have,
and the buyer/seller lists are caller-scoped — so an admin who wanted to send a
realtor to a property had no way to name the deal.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _seed_transaction(
    db_engine: Engine,
    *,
    buyer: UUID,
    seller: UUID,
    listing: UUID,
    stage: str = "offer_accepted",
) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :price, :stage)"
            ),
            {
                "id": tx_id,
                "lid": listing,
                "bid": buyer,
                "sid": seller,
                "price": 5_000_000_00,
                "stage": stage,
            },
        )
    return tx_id


@pytest.mark.asyncio
async def test_admin_sees_live_deals_with_the_property(
    clean_tables: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin = seed_user(role="admin")
    listing = seed_listing(seller_id=seller)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get(
        "/admin/transactions", headers=auth_header(mint_token(admin, "admin"))
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(tx_id)
    # The property is the whole point — an admin choosing where to send a realtor
    # cannot work from transaction ids.
    assert item["property_title"] == "Plot"
    assert item["state"] == "Lagos"


@pytest.mark.asyncio
async def test_parties_are_references_not_identities(
    clean_tables: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Contact masking (§10) does not stop at the buyer and seller's own screens:
    the picker shows 8-char refs so two deals on one listing can be told apart,
    and nothing more."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin = seed_user(role="admin")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get(
        "/admin/transactions", headers=auth_header(mint_token(admin, "admin"))
    )

    item = resp.json()["items"][0]
    assert item["buyer_ref"] == str(buyer)[:8]
    assert item["seller_ref"] == str(seller)[:8]
    assert "buyer_id" not in item and "seller_id" not in item


@pytest.mark.asyncio
async def test_finished_deals_are_excluded(
    clean_tables: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """An inspection on a completed or cancelled deal is never the intent, and
    listing them would bury the deals an admin can actually act on."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin = seed_user(role="admin")
    listing = seed_listing(seller_id=seller)
    live = _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)
    for stage in ("completed", "cancelled"):
        _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing, stage=stage)

    resp = await http_client.get(
        "/admin/transactions", headers=auth_header(mint_token(admin, "admin"))
    )

    assert [item["id"] for item in resp.json()["items"]] == [str(live)]


@pytest.mark.asyncio
async def test_search_matches_the_property_title_and_the_transaction_id(
    clean_tables: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """An admin working from a support conversation has one or the other."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin = seed_user(role="admin")
    listing = seed_listing(seller_id=seller)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)
    headers = auth_header(mint_token(admin, "admin"))

    by_title = await http_client.get("/admin/transactions?search=plo", headers=headers)
    by_id = await http_client.get(f"/admin/transactions?search={tx_id}", headers=headers)
    miss = await http_client.get("/admin/transactions?search=nothinghere", headers=headers)

    assert [i["id"] for i in by_title.json()["items"]] == [str(tx_id)]
    assert [i["id"] for i in by_id.json()["items"]] == [str(tx_id)]
    assert miss.json()["items"] == []


@pytest.mark.asyncio
async def test_non_admins_are_refused(
    clean_tables: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """The list spans every party's deals, so the admin gate is the only thing
    keeping one buyer from reading the whole marketplace."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get(
        "/admin/transactions", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.status_code == 403
