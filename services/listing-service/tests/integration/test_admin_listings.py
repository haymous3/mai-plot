"""The admin listing console — browse + detail (SCRUM-215).

The gap these pin: the whole admin listing surface was a queue pinned to
`status=pending_review`, so an approved listing left the admin's world entirely
(13 of 14 on staging), and the approve/reject decision was made from a table row
with no photo, no description, no address and no documents.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Every status the DB CHECK allows (listing migrations 0001 + 0004).
_ALL_STATUSES = [
    "pending_review",
    "active",
    "under_offer",
    "sold",
    "expired",
    "rejected",
    "paused",
]


@pytest.fixture
def admin_token(
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> dict[str, str]:
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    return auth_header(mint_access_token(admin, "admin"))


@pytest.mark.asyncio
async def test_browse_returns_every_status_not_just_pending(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """The bug in one assertion: the review queue shows 1 of these, the console
    shows all 7."""
    seller = seed_seller(phone="08012345678")
    for status in _ALL_STATUSES:
        seed_listing(seller_id=seller, status=status, title=f"Plot {status}")

    console = await http_client.get("/admin/listings", headers=admin_token)
    queue = await http_client.get("/admin/listings/queue", headers=admin_token)

    assert console.status_code == 200, console.text
    assert console.json()["pagination"]["total"] == len(_ALL_STATUSES)
    assert queue.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_browse_filters_by_status(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    seller = seed_seller(phone="08012345678")
    seed_listing(seller_id=seller, status="active", title="Live one")
    seed_listing(seller_id=seller, status="paused", title="Paused one")

    resp = await http_client.get("/admin/listings?status=paused", headers=admin_token)

    assert [item["title"] for item in resp.json()["data"]] == ["Paused one"]


@pytest.mark.asyncio
async def test_browse_searches_title_and_address(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """An admin working from a support conversation has a street or a name."""
    seller = seed_seller(phone="08012345678")
    wanted = seed_listing(seller_id=seller, status="active", title="Duplex on Admiralty")
    seed_listing(seller_id=seller, status="active", title="Somewhere else entirely")

    by_title = await http_client.get("/admin/listings?search=admiralty", headers=admin_token)
    # The fixture's address is "1 Demo St, Lagos" for every row, so an address
    # hit is proved by matching a term that appears in NO title.
    by_address = await http_client.get("/admin/listings?search=demo st", headers=admin_token)
    miss = await http_client.get("/admin/listings?search=nothinghere", headers=admin_token)

    assert [i["id"] for i in by_title.json()["data"]] == [str(wanted)]
    assert by_address.json()["pagination"]["total"] == 2
    assert miss.json()["data"] == []


@pytest.mark.asyncio
async def test_browse_hides_soft_deleted_listings(
    clean_listing_tables: None,
    disable_cache: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """A deleted listing is not one an admin acts on, and surfacing it here would
    make `deleted_at` look advisory."""
    seller = seed_seller(phone="08012345678")
    gone = seed_listing(seller_id=seller, status="active", title="Deleted")
    seed_listing(seller_id=seller, status="active", title="Live")
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE property_listings SET deleted_at = NOW() WHERE id = :id"), {"id": gone}
        )

    resp = await http_client.get("/admin/listings", headers=admin_token)

    assert [i["title"] for i in resp.json()["data"]] == ["Live"]


@pytest.mark.asyncio
async def test_detail_carries_what_a_decision_needs(
    clean_listing_tables: None,
    disable_cache: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """Photo, description, address and coordinates — none of which the queue row
    carried, though the queue is where listings get approved."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review", title="Duplex")
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE property_listings SET description = :d WHERE id = :id"),
            {"d": "Spacious, all ensuite.", "id": listing_id},
        )
        conn.execute(
            text(
                "INSERT INTO listing_media (listing_id, media_type, s3_key, cdn_url, "
                "sort_order, size_bytes) VALUES (:lid, 'photo', 'k/1.jpg', "
                "'https://cdn/1.jpg', 0, 1024)"
            ),
            {"lid": listing_id},
        )

    resp = await http_client.get(f"/admin/listings/{listing_id}", headers=admin_token)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["description"] == "Spacious, all ensuite."
    assert body["address_text"]
    assert body["location"]["lat"] and body["location"]["lng"]
    assert [m["url"] for m in body["media"]] == ["https://cdn/1.jpg"]
    assert body["seller"]["id"] == str(seller)


@pytest.mark.asyncio
async def test_detail_includes_the_audit_history(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """ "Who did this, and when" is the question an admin opens a listing with."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review")

    await http_client.post(
        f"/admin/listings/{listing_id}/review", json={"action": "approve"}, headers=admin_token
    )
    resp = await http_client.get(f"/admin/listings/{listing_id}", headers=admin_token)

    history = resp.json()["history"]
    assert [h["action"] for h in history] == ["listing.active"]
    assert history[0]["actor_role"] == "admin"
    assert history[0]["new_value"]["status"] == "active"


@pytest.mark.asyncio
async def test_detail_does_not_bump_the_sellers_view_count(
    clean_listing_tables: None,
    disable_cache: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """Serving the admin from the public detail endpoint would inflate a metric
    the seller is shown — which is why this reads its own row."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")

    for _ in range(3):
        await http_client.get(f"/admin/listings/{listing_id}", headers=admin_token)

    with db_engine.connect() as conn:
        views = conn.execute(
            text("SELECT view_count FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).scalar_one()
    assert views == 0


@pytest.mark.asyncio
async def test_detail_survives_a_deleted_seller(
    clean_listing_tables: None,
    disable_cache: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    admin_token: dict[str, str],
) -> None:
    """An orphaned listing is exactly what an admin opens this page to find, so
    it must not 404 on the way to being found."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE users SET deleted_at = NOW() WHERE id = :id"), {"id": seller})

    resp = await http_client.get(f"/admin/listings/{listing_id}", headers=admin_token)

    assert resp.status_code == 200
    assert resp.json()["seller"]["id"] == str(seller)
    assert resp.json()["seller"]["authority_type"] is None


@pytest.mark.asyncio
async def test_unknown_listing_is_404(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    admin_token: dict[str, str],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    resp = await http_client.get(f"/admin/listings/{uuid4()}", headers=admin_token)

    assert resp.status_code == 404
    assert_error_envelope(resp.json(), "LISTING_NOT_FOUND")


@pytest.mark.asyncio
async def test_non_admins_are_refused(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """The console spans every seller's listings in every status, so the admin
    gate is the only thing keeping one seller from reading the whole book."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")
    headers = auth_header(mint_access_token(seller, "seller"))

    browse = await http_client.get("/admin/listings", headers=headers)
    detail = await http_client.get(f"/admin/listings/{listing_id}", headers=headers)

    assert browse.status_code == 403
    assert detail.status_code == 403
