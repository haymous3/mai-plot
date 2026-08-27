"""GET /transactions/active-deals integration tests (SCRUM-188).

Backs auth-service's account-deletion guard. The property under test is that a
user with ANY non-terminal deal, in ANY party role, is reported as active — an
undercount here would let someone delete an account with money still in motion.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

# 'completed' and 'cancelled' are the only stages with no outgoing transitions
# in state_machine._TRANSITIONS. Everything else keeps an account alive.
_TERMINAL = ["completed", "cancelled"]
_ACTIVE = [
    "offer_accepted",
    "inspection_scheduled",
    "inspection_completed",
    "loan_applied",
    "loan_approved",
    "loan_rejected",
    "payment_held",
    "title_held",
    "disputed",
    "resolved",
]


def _seed_transaction(
    db_engine: Engine,
    *,
    buyer: UUID,
    seller: UUID,
    listing: UUID,
    stage: str,
    realtor: UUID | None = None,
) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "realtor_id, agreed_price_kobo, stage) "
                "VALUES (:id, :lid, :bid, :sid, :rid, :price, :stage)"
            ),
            {
                "id": tx_id,
                "lid": listing,
                "bid": buyer,
                "sid": seller,
                "rid": realtor,
                "price": 5_000_000_00,
                "stage": stage,
            },
        )
    return tx_id


@pytest.mark.asyncio
async def test_no_deals_reports_clear(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.status_code == 200
    assert resp.json() == {"active_count": 0, "has_active": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", _ACTIVE)
async def test_every_non_terminal_stage_counts_as_active(
    stage: str,
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Parametrised over the whole stage list on purpose: adding a stage to the
    state machine without revisiting this guard would silently let an account
    in that stage be deleted. 'disputed' matters most — a dispute is precisely
    when an account must not vanish."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing, stage=stage)

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.json() == {"active_count": 1, "has_active": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", _TERMINAL)
async def test_terminal_stages_do_not_block(
    stage: str,
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing, stage=stage)

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.json() == {"active_count": 0, "has_active": False}


@pytest.mark.asyncio
async def test_the_seller_side_counts_too(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Role-agnostic: the query matches either side, so one endpoint serves
    buyers and sellers."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing, stage="payment_held")

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(seller, "seller"))
    )

    assert resp.json() == {"active_count": 1, "has_active": True}


@pytest.mark.asyncio
async def test_the_assigned_realtor_counts_too(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """`realtor_id` is on the transactions table (migration 0001) even though
    app/models/transaction.py does not map it — the assigned realtor is a party
    to a live deal, so the query covers all three columns."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    realtor = seed_user(role="realtor")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(
        db_engine,
        buyer=buyer,
        seller=seller,
        listing=listing,
        stage="inspection_scheduled",
        realtor=realtor,
    )

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(realtor, "realtor"))
    )

    assert resp.json() == {"active_count": 1, "has_active": True}


@pytest.mark.asyncio
async def test_another_users_deal_does_not_count(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """A stranger's live deal must not block this user's deletion."""
    buyer = seed_user(role="buyer")
    other = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(db_engine, buyer=other, seller=seller, listing=listing, stage="payment_held")

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.json() == {"active_count": 0, "has_active": False}


@pytest.mark.asyncio
async def test_counts_several_live_deals(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    for stage in ("offer_accepted", "payment_held", "completed"):
        _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing, stage=stage)

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.json() == {"active_count": 2, "has_active": True}


@pytest.mark.asyncio
async def test_requires_authentication(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    """Caller-scoped by JWT — there is no user_id parameter to abuse, so one
    user can never probe another's deal state through this endpoint."""
    resp = await http_client.get("/transactions/active-deals")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_path_is_not_captured_as_a_transaction_id(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Declared before the `/{transaction_id}/...` routes. If that ordering
    regressed, "active-deals" would be parsed as a UUID and 422."""
    buyer = seed_user(role="buyer")

    resp = await http_client.get(
        "/transactions/active-deals", headers=auth_header(mint_token(buyer, "buyer"))
    )

    assert resp.status_code == 200
