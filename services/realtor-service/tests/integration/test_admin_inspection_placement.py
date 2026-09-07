"""Integration tests for admin inspection placement (SCRUM-208).

Covers the queue of requests nobody could be assigned to, placing one with a
chosen realtor, and an admin creating an assignment outright.

The fixtures deliberately seed a realtor FAR from the property (or with no
base_location at all) so the auto-assign path finds nobody — that is the state
this feature exists for, and per SCRUM-208 it is also the state every realtor
who onboards through the product is in, since onboarding collects no location.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.asyncio

_PROP_LNG, _PROP_LAT = 3.4, 6.5


def _seed_listing(conn: object, seller_id: UUID) -> UUID:
    listing_id = uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO property_listings
                (id, seller_id, property_type, title, address_text, location,
                 lga, state, asking_price_kobo, sale_type, status)
            VALUES
                (:id, :sid, 'land', 'Ikeja Plot', '1 St',
                 ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                 'Ikeja', 'Lagos', 5000000000, 'normal', 'active')
            """
        ),
        {"id": listing_id, "sid": seller_id, "lng": _PROP_LNG, "lat": _PROP_LAT},
    )
    return listing_id


def _seed_transaction(conn: object, *, listing_id: UUID, buyer_id: UUID, seller_id: UUID) -> UUID:
    tx_id = uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, agreed_price_kobo) "
            "VALUES (:id, :lid, :bid, :sid, 5000000000)"
        ),
        {"id": tx_id, "lid": listing_id, "bid": buyer_id, "sid": seller_id},
    )
    return tx_id


def _seed_realtor(
    conn: object,
    *,
    status: str = "approved",
    full_name: str = "Ada Realtor",
    lng: float | None = None,
    lat: float | None = None,
) -> UUID:
    """A realtor with NO base_location by default — the shape every UI signup has."""
    user_id = uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO users (id, role, verified_status, is_active) "
            "VALUES (:id, 'realtor', 'id_verified', TRUE)"
        ),
        {"id": user_id},
    )
    conn.execute(  # type: ignore[attr-defined]
        text("INSERT INTO user_pii (user_id, phone, full_name) VALUES (:id, :phone, :name)"),
        {"id": user_id, "phone": f"+234{uuid4().int % 10**10:010d}", "name": full_name},
    )
    location = (
        "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
        if lng is not None and lat is not None
        else "NULL"
    )
    params: dict[str, object] = {"id": user_id, "status": status}
    if lng is not None and lat is not None:
        params |= {"lng": lng, "lat": lat}
    conn.execute(  # type: ignore[attr-defined]
        text(
            f"""
            INSERT INTO realtors
                (id, coverage_states, government_id_s3_key, approval_status, base_location)
            VALUES
                (:id, ARRAY['Lagos'], 'realtor-id/x.pdf', :status, {location})
            """
        ),
        params,
    )
    return user_id


def _proposed() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


async def _request_unassigned(
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> tuple[UUID, str]:
    """A buyer requests an inspection with nobody in range → an unassigned row.
    Returns (transaction_id, inspection_id)."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
    resp = await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "unassigned"
    return tx_id, resp.json()["id"]


async def test_queue_lists_the_waiting_request(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    _, inspection_id = await _request_unassigned(
        http_client, db_engine, seed_user, mint_token, auth_header
    )
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get("/admin/inspections/unassigned", headers=admin)

    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["id"] == inspection_id)
    assert item["property_title"] == "Ikeja Plot"
    assert item["state"] == "Lagos"
    assert item["property_located"] is True
    # §10: the parties are references, never names or contacts.
    assert len(item["buyer_ref"]) == 8
    assert "full_name" not in item


async def test_queue_requires_admin(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    assert (await http_client.get("/admin/inspections/unassigned")).status_code == 401
    realtor = seed_user(role="realtor")
    forbidden = await http_client.get(
        "/admin/inspections/unassigned", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert forbidden.status_code == 403


async def test_assignable_realtors_includes_one_with_no_location(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """The picker must show the realtors proximity CANNOT reach — they are the
    whole reason manual placement exists (SCRUM-208 finding 3)."""
    with db_engine.begin() as conn:
        approved = _seed_realtor(conn, status="approved", full_name="Bola Approved")
        _seed_realtor(conn, status="pending", full_name="Chidi Pending")
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get("/admin/inspections/assignable-realtors", headers=admin)

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = [i["id"] for i in items]
    assert str(approved) in ids
    # A pending application is not assignable — approval is the one gate manual
    # placement does NOT bypass.
    assert len(items) == 1
    assert items[0]["has_base_location"] is False


async def test_place_assigns_and_audits(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    _, inspection_id = await _request_unassigned(
        http_client, db_engine, seed_user, mint_token, auth_header
    )
    with db_engine.begin() as conn:
        realtor = _seed_realtor(conn)  # approved, no base_location
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        f"/admin/inspections/{inspection_id}/assign",
        json={"realtor_id": str(realtor)},
        headers=admin,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["realtor_id"] == str(realtor)
    assert body["status"] == "pending"
    # The acceptance window opens only now — it belongs to the offer.
    assert body["assignment_expires_at"] is not None

    with db_engine.connect() as conn:
        action = conn.execute(
            text(
                "SELECT action FROM audit_log WHERE entity_type = 'inspection' "
                "AND entity_id = :id ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": inspection_id},
        ).scalar_one()
    assert action == "inspection.placed_by_admin"

    # And the realtor now sees it on their own dashboard feed.
    mine = await http_client.get(
        "/inspections/mine", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert mine.status_code == 200
    # The realtor feed keys the inspection as `inspection_id`, not `id`.
    assert [i["inspection_id"] for i in mine.json()["data"]] == [inspection_id]


async def test_place_twice_is_409(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Two admins clicking Assign: the guarded UPDATE is the arbiter, so the
    second gets 409 rather than silently stealing the assignment."""
    _, inspection_id = await _request_unassigned(
        http_client, db_engine, seed_user, mint_token, auth_header
    )
    with db_engine.begin() as conn:
        first = _seed_realtor(conn, full_name="First")
        second = _seed_realtor(conn, full_name="Second")
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    ok = await http_client.post(
        f"/admin/inspections/{inspection_id}/assign",
        json={"realtor_id": str(first)},
        headers=admin,
    )
    assert ok.status_code == 200
    clash = await http_client.post(
        f"/admin/inspections/{inspection_id}/assign",
        json={"realtor_id": str(second)},
        headers=admin,
    )
    assert clash.status_code == 409
    assert clash.json()["error_code"] == "INSPECTION_NOT_UNASSIGNED"


async def test_place_with_unapproved_realtor_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Manual placement bypasses the RADIUS, never the APPROVAL — an unvetted
    person must not be sent to meet a buyer at a property."""
    _, inspection_id = await _request_unassigned(
        http_client, db_engine, seed_user, mint_token, auth_header
    )
    with db_engine.begin() as conn:
        pending = _seed_realtor(conn, status="pending")
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        f"/admin/inspections/{inspection_id}/assign",
        json={"realtor_id": str(pending)},
        headers=admin,
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "REALTOR_NOT_ASSIGNABLE"


async def test_place_unknown_inspection_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    with db_engine.begin() as conn:
        realtor = _seed_realtor(conn)
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))
    resp = await http_client.post(
        f"/admin/inspections/{uuid4()}/assign", json={"realtor_id": str(realtor)}, headers=admin
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "INSPECTION_NOT_FOUND"


async def test_admin_creates_an_inspection_with_a_named_realtor(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """The path that works today: an admin puts an inspection on a realtor's
    dashboard for a transaction, with no buyer request needed — nothing in the
    product calls POST /inspections yet (SCRUM-208 finding 2)."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        realtor = _seed_realtor(conn)
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        "/admin/inspections",
        json={
            "transaction_id": str(tx_id),
            "proposed_date": _proposed(),
            "realtor_id": str(realtor),
        },
        headers=admin,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["realtor_id"] == str(realtor)
    assert body["status"] == "pending"
    assert body["auto_assigned"] is False

    with db_engine.connect() as conn:
        action = conn.execute(
            text(
                "SELECT action FROM audit_log WHERE entity_type = 'inspection' "
                "AND entity_id = :id ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": body["id"]},
        ).scalar_one()
    assert action == "inspection.created_by_admin"


async def test_admin_create_without_a_realtor_uses_proximity(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        near = _seed_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        "/admin/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=admin,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["realtor_id"] == str(near)
    assert resp.json()["auto_assigned"] is True


async def test_admin_create_without_a_realtor_and_nobody_in_range_is_503(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Unlike the buyer path, this FAILS rather than parking a row: the admin
    asked us to choose, so they are owed the answer that we could not."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        _seed_realtor(conn)  # approved but no base_location
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        "/admin/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=admin,
    )

    assert resp.status_code == 503
    assert resp.json()["error_code"] == "NO_REALTOR_IN_RANGE"


async def test_admin_create_rejects_a_past_date(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        realtor = _seed_realtor(conn)
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        "/admin/inspections",
        json={
            "transaction_id": str(tx_id),
            "proposed_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "realtor_id": str(realtor),
        },
        headers=admin,
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "PROPOSED_DATE_INVALID"


async def test_a_waiting_request_blocks_a_second_one(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """An unassigned request counts as live: otherwise a buyer refreshing the
    page fills the admin queue with duplicates of the same ask."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
    headers = auth_header(mint_token(buyer, "buyer"))
    payload = {"transaction_id": str(tx_id), "proposed_date": _proposed()}

    first = await http_client.post("/inspections", json=payload, headers=headers)
    assert first.status_code == 201
    second = await http_client.post("/inspections", json=payload, headers=headers)

    assert second.status_code == 409
    assert second.json()["error_code"] == "INSPECTION_ALREADY_ACTIVE"
