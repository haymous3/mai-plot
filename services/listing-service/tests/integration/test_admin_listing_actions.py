"""Admin power over a LIVE listing (SCRUM-215).

Admin control stopped at the front door: approve or reject once while the
listing was `pending_review`, and nothing afterwards. A listing that turned out
to be fraudulent or duplicated stayed on the marketplace with no way to remove
it.

Also pins the re-index bug these actions would otherwise have inherited — see
test_pausing_removes_the_listing_from_search.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.fixture
def admin_token(
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> dict[str, str]:
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    return auth_header(mint_access_token(admin, "admin"))


def _status(db_engine: Engine, listing_id: UUID) -> str:
    with db_engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
            ).scalar_one()
        )


@pytest.mark.asyncio
async def test_pause_and_unpause_round_trip(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    paused = await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "pause"}, headers=admin_token
    )
    assert paused.status_code == 200, paused.text
    assert _status(db_engine, listing_id) == "paused"

    resumed = await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "unpause"}, headers=admin_token
    )
    assert resumed.status_code == 200, resumed.text
    assert _status(db_engine, listing_id) == "active"


@pytest.mark.asyncio
async def test_take_down_records_the_reason_the_seller_sees(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """Take-down reuses `rejected` + `rejection_reason`, so it reads to the owner
    exactly like a rejection — no new seller-facing concept."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    resp = await http_client.post(
        f"/admin/listings/{listing_id}/status",
        json={"action": "take_down", "reason": "Duplicate of an existing listing."},
        headers=admin_token,
    )

    assert resp.status_code == 200, resp.text
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, rejection_reason FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).first()
    assert row is not None
    assert row.status == "rejected"
    assert row.rejection_reason == "Duplicate of an existing listing."


@pytest.mark.asyncio
async def test_take_down_without_a_reason_is_422(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    resp = await http_client.post(
        f"/admin/listings/{listing_id}/status",
        json={"action": "take_down", "reason": "   "},
        headers=admin_token,
    )

    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "REASON_REQUIRED")
    assert _status(db_engine, listing_id) == "active"


@pytest.mark.asyncio
async def test_resuming_clears_a_stale_takedown_reason(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """A listing paused and resumed must not keep showing its owner the reason it
    was taken down last month."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE property_listings SET status = 'paused', "
                "rejection_reason = 'an old reason' WHERE id = :id"
            ),
            {"id": listing_id},
        )

    await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "unpause"}, headers=admin_token
    )

    with db_engine.connect() as conn:
        reason = conn.execute(
            text("SELECT rejection_reason FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).scalar_one()
    assert reason is None


@pytest.mark.asyncio
async def test_an_under_offer_listing_is_refused_with_its_own_code(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    """§8 rule 4: an accepted offer holds the listing for 72 hours and there may
    be escrow behind it. Pulling it out from under a live transaction is a deal
    decision, not a listing one — and the remedy is different, so the code is."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="under_offer")

    for action in ("pause", "take_down", "expire"):
        resp = await http_client.post(
            f"/admin/listings/{listing_id}/status",
            json={"action": action, "reason": "because"},
            headers=admin_token,
        )
        assert resp.status_code == 422, action
        assert_error_envelope(resp.json(), "LISTING_UNDER_OFFER")

    assert _status(db_engine, listing_id) == "under_offer"


@pytest.mark.asyncio
async def test_a_sold_listing_cannot_be_acted_on(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="sold")

    resp = await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "pause"}, headers=admin_token
    )

    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "LISTING_STATUS_CONFLICT")
    assert _status(db_engine, listing_id) == "sold"


@pytest.mark.asyncio
async def test_expire_applies_the_sweeps_transition_early(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    resp = await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "expire"}, headers=admin_token
    )

    assert resp.status_code == 200, resp.text
    assert _status(db_engine, listing_id) == "expired"


@pytest.mark.asyncio
async def test_every_action_writes_an_audit_row(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """Listing state changes are audited (§4), and the history is what the admin
    detail page reads back."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "pause"}, headers=admin_token
    )

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT action, old_value, new_value FROM audit_log "
                "WHERE entity_id = :id AND entity_type = 'listing'"
            ),
            {"id": listing_id},
        ).first()
    assert row is not None
    assert row.action == "listing.paused_by_admin"
    assert row.old_value["status"] == "active"
    assert row.new_value["status"] == "paused"


@pytest.mark.asyncio
async def test_pausing_removes_the_listing_from_search(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """⚠️ THE BUG THIS TICKET FOUND, from the admin side.

    `paused` is not in INDEXABLE_STATUSES, but the pause path never re-indexed:
    the ES document kept `status: "active"`, which is the exact term the search
    query filters on, so a paused listing stayed findable. The feed hid it (that
    reads the DB), which is why nobody noticed.
    """
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review", title="Findable Duplex")
    # Reach the index the way a real listing does: approval indexes it.
    await http_client.post(
        f"/admin/listings/{listing_id}/review", json={"action": "approve"}, headers=admin_token
    )
    seeded = await http_client.get("/listings/search", params={"q": "findable"})
    assert seeded.json()["pagination"]["total"] == 1, "precondition: it should be searchable"

    await http_client.post(
        f"/admin/listings/{listing_id}/status", json={"action": "pause"}, headers=admin_token
    )

    after = await http_client.get("/listings/search", params={"q": "findable"})
    assert after.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_seller_pause_also_removes_it_from_search(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    admin_token: dict[str, str],
) -> None:
    """The same bug from the SELLER side, which is where it actually shipped:
    `SellerListingsService` was constructed with no IndexDispatcher at all."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review", title="Seller Duplex")
    await http_client.post(
        f"/admin/listings/{listing_id}/review", json={"action": "approve"}, headers=admin_token
    )
    seeded = await http_client.get("/listings/search", params={"q": "seller"})
    assert seeded.json()["pagination"]["total"] == 1, "precondition: it should be searchable"

    resp = await http_client.post(
        f"/listings/{listing_id}/pause",
        headers=auth_header(mint_access_token(seller, "seller")),
    )
    assert resp.status_code == 200, resp.text

    after = await http_client.get("/listings/search", params={"q": "seller"})
    assert after.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_unknown_listing_is_404(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    admin_token: dict[str, str],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    resp = await http_client.post(
        f"/admin/listings/{uuid4()}/status", json={"action": "pause"}, headers=admin_token
    )

    assert resp.status_code == 404
    assert_error_envelope(resp.json(), "LISTING_NOT_FOUND")


@pytest.mark.asyncio
async def test_non_admins_cannot_act(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Not even the owner: the seller has their own pause endpoint, and take-down
    is not a power a seller should hold over their own listing's audit trail."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    resp = await http_client.post(
        f"/admin/listings/{listing_id}/status",
        json={"action": "take_down", "reason": "mine now"},
        headers=auth_header(mint_access_token(seller, "seller")),
    )

    assert resp.status_code == 403
    assert _status(db_engine, listing_id) == "active"
