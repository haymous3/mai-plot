"""PUT /realtors/me/base-location — making a realtor reachable by proximity (SCRUM-214).

The point of the endpoint is the last test: a realtor with no base location is
invisible to the admin "choose for me" path, and setting one through this
endpoint is what makes them findable.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.integration.test_admin_inspection_placement import (
    _PROP_LAT,
    _PROP_LNG,
    _proposed,
    _seed_listing,
    _seed_realtor,
    _seed_transaction,
)

pytestmark = pytest.mark.asyncio


async def test_setting_a_base_is_read_back_on_the_profile(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    db_engine: Engine,
) -> None:
    realtor = seed_realtor(status="approved")
    headers = auth_header(mint_token(realtor, "realtor"))

    before = await http_client.get("/realtors/me", headers=headers)
    assert before.json()["base_lat"] is None

    put = await http_client.put(
        "/realtors/me/base-location", json={"lat": 6.4474, "lng": 3.4553}, headers=headers
    )
    assert put.status_code == 200, put.text
    assert put.json()["base_lat"] == pytest.approx(6.4474)
    assert put.json()["base_lng"] == pytest.approx(3.4553)

    after = await http_client.get("/realtors/me", headers=headers)
    assert after.json()["base_lat"] == pytest.approx(6.4474)

    with db_engine.connect() as conn:
        audited = conn.execute(
            text(
                "SELECT new_value FROM audit_log "
                "WHERE action = 'realtor.base_location_set' AND actor_id = :u"
            ),
            {"u": realtor},
        ).scalar_one()
    assert audited == {"lat": 6.447, "lng": 3.455}


async def test_a_base_outside_nigeria_is_422_and_nothing_changes(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="approved")
    headers = auth_header(mint_token(realtor, "realtor"))

    resp = await http_client.put(
        "/realtors/me/base-location", json={"lat": 51.5, "lng": -0.12}, headers=headers
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "LOCATION_OUTSIDE_NIGERIA"
    assert (await http_client.get("/realtors/me", headers=headers)).json()["base_lat"] is None


async def test_setting_a_base_needs_a_realtor_profile_and_role(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    body = {"lat": 6.5, "lng": 3.4}

    not_onboarded = seed_user(role="realtor")
    r1 = await http_client.put(
        "/realtors/me/base-location",
        json=body,
        headers=auth_header(mint_token(not_onboarded, "realtor")),
    )
    assert r1.status_code == 404
    assert r1.json()["error_code"] == "REALTOR_NOT_FOUND"

    buyer = seed_user(role="buyer")
    r2 = await http_client.put(
        "/realtors/me/base-location", json=body, headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert r2.status_code == 403


async def test_setting_a_base_makes_the_realtor_reachable_by_proximity(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """The whole ticket: the shape every UI signup had (approved, no base) is
    unreachable; after they set a base near the property, "choose for me" picks
    them."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    with db_engine.begin() as conn:
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        realtor = _seed_realtor(conn)  # approved, no base_location
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))
    place = {"transaction_id": str(tx_id), "proposed_date": _proposed()}

    unreachable = await http_client.post("/admin/inspections", json=place, headers=admin)
    assert unreachable.status_code == 503

    put = await http_client.put(
        "/realtors/me/base-location",
        json={"lat": _PROP_LAT + 0.05, "lng": _PROP_LNG + 0.05},  # ~8 km away
        headers=auth_header(mint_token(realtor, "realtor")),
    )
    assert put.status_code == 200, put.text

    reachable = await http_client.post("/admin/inspections", json=place, headers=admin)
    assert reachable.status_code == 201, reachable.text
    assert reachable.json()["realtor_id"] == str(realtor)
    assert reachable.json()["auto_assigned"] is True
