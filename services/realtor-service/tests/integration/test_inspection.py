"""Integration tests for inspection auto-assignment (SCRUM-72).

Seeds a property (with a PostGIS location), a transaction, and an approved
realtor with a base_location, then exercises request/accept + the
no-realtor-in-range fallback.
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

# Property is at (lng=3.4, lat=6.5). A realtor at the same point is ~0 km;
# +1.5 deg latitude is ~166 km (well beyond the 50 km radius).
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
                (:id, :sid, 'land', 'Plot', '1 St',
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


def _seed_approved_realtor(
    conn: object, *, lng: float, lat: float, full_name: str = "Ada Realtor"
) -> tuple[UUID, str]:
    user_id = uuid4()
    esvarbon = f"ESV/{uuid4().hex[:8].upper()}"
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
    conn.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO realtors
                (id, esvarbon_number, coverage_states, government_id_s3_key,
                 approval_status, base_location)
            VALUES
                (:id, :esv, ARRAY['Lagos'], 'realtor-id/x.pdf', 'approved',
                 ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography)
            """
        ),
        {"id": user_id, "esv": esvarbon, "lng": lng, "lat": lat},
    )
    return user_id, esvarbon


def _proposed() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


async def test_request_assigns_nearest_realtor(
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
        realtor, _ = _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)  # ~0 km

    resp = await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["realtor_id"] == str(realtor)
    assert body["status"] == "pending"

    # The assigned realtor accepts within the window.
    accept = await http_client.post(
        f"/inspections/{body['id']}/accept", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["status"] == "accepted"


async def test_request_no_realtor_in_range_is_503(
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
        _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT + 1.5)  # ~166 km away

    resp = await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "NO_REALTOR_AVAILABLE"


async def test_request_by_non_party_is_403(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    stranger = seed_user(role="buyer")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)

    resp = await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(stranger, "buyer")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_TRANSACTION_PARTY"


async def test_accept_by_wrong_realtor_is_403(
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
        _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)

    created = await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    inspection_id = created.json()["id"]

    other_realtor = seed_user(role="realtor")
    resp = await http_client.post(
        f"/inspections/{inspection_id}/accept",
        headers=auth_header(mint_token(other_realtor, "realtor")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_ASSIGNED_REALTOR"


# -- GET /inspections/by-transaction/{tx} (SCRUM-139) ----------------------


async def test_assigned_realtor_visible_to_seller(
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
        realtor, esvarbon = _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)

    # Buyer requests → auto-assigned.
    await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )

    # Seller sees the assigned realtor's name + licence (no contact details).
    resp = await http_client.get(
        f"/inspections/by-transaction/{tx_id}",
        headers=auth_header(mint_token(seller, "seller")),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["assigned"] is True
    assert body["realtor_name"] == "Ada Realtor"
    assert body["esvarbon_number"] == esvarbon
    assert body["status"] == "pending"
    assert "phone" not in body and "email" not in body


async def test_assigned_realtor_none_when_no_inspection(
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

    resp = await http_client.get(
        f"/inspections/by-transaction/{tx_id}",
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "assigned": False,
        "inspection_id": None,
        "realtor_name": None,
        "esvarbon_number": None,
        "status": None,
        "proposed_date": None,
        "confirmed_date": None,
    }


async def test_assigned_realtor_forbidden_for_non_party(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    stranger = seed_user(role="buyer")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)

    resp = await http_client.get(
        f"/inspections/by-transaction/{tx_id}",
        headers=auth_header(mint_token(stranger, "buyer")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_TRANSACTION_PARTY"


# -- GET /inspections/mine (SCRUM-140) -------------------------------------


async def test_mine_lists_assigned_inspection_with_property(
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
        realtor, _ = _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)

    # Buyer requests → auto-assigned to the realtor.
    created = await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    inspection_id = created.json()["id"]

    resp = await http_client.get(
        "/inspections/mine", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["inspection_id"] == inspection_id
    assert item["transaction_id"] == str(tx_id)
    assert item["status"] == "pending"
    assert item["property_title"] == "Plot"
    assert item["address_text"] == "1 St"
    assert item["state"] == "Lagos"


async def test_mine_empty_for_realtor_without_assignments(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    resp = await http_client.get(
        "/inspections/mine", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"data": []}


async def test_mine_excludes_other_realtors_assignments(
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
        _seed_approved_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)

    await http_client.post(
        "/inspections",
        json={"transaction_id": str(tx_id), "proposed_date": _proposed()},
        headers=auth_header(mint_token(buyer, "buyer")),
    )

    # A different realtor sees none of it.
    other = seed_user(role="realtor")
    resp = await http_client.get(
        "/inspections/mine", headers=auth_header(mint_token(other, "realtor"))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"data": []}
