"""Integration tests for inspection report submission/viewing (SCRUM-73)."""

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
_JPEG = b"\xff\xd8\xff\xe0 inspection photo"


def _seed_world(db_engine: Engine, *, buyer: UUID, seller: UUID, realtor: UUID) -> UUID:
    """Seed a listing + transaction + an accepted inspection (confirmed in the
    past so a report can be submitted). Returns the inspection id."""
    listing_id, tx_id, inspection_id = uuid4(), uuid4(), uuid4()
    past = datetime.now(UTC) - timedelta(hours=1)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO property_listings
                    (id, seller_id, property_type, title, address_text, location,
                     lga, state, asking_price_kobo, sale_type, status)
                VALUES (:id, :sid, 'land', 'Plot', '1 St',
                     ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                     'Ikeja', 'Lagos', 5000000000, 'normal', 'active')
                """
            ),
            {"id": listing_id, "sid": seller, "lng": _PROP_LNG, "lat": _PROP_LAT},
        )
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, agreed_price_kobo) "
                "VALUES (:id, :lid, :bid, :sid, 5000000000)"
            ),
            {"id": tx_id, "lid": listing_id, "bid": buyer, "sid": seller},
        )
        conn.execute(
            text(
                """
                INSERT INTO inspections
                    (id, transaction_id, realtor_id, proposed_date, confirmed_date,
                     status, assignment_expires_at)
                VALUES (:id, :tx, :realtor, :past, :past, 'accepted', :past)
                """
            ),
            {"id": inspection_id, "tx": tx_id, "realtor": realtor, "past": past},
        )
    return inspection_id


def _photos(n: int = 3) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("photos", (f"p{i}.jpg", _JPEG, "image/jpeg")) for i in range(n)]


def _form(lng: float = _PROP_LNG, lat: float = _PROP_LAT) -> dict[str, object]:
    return {
        "gps_lat": str(lat),
        "gps_lng": str(lng),
        "property_condition": "good",
        "amenities": ["water", "power"],
        "remarks": "Looks fine",
    }


async def test_submit_and_view_report(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    inspection_id = _seed_world(db_engine, buyer=buyer, seller=seller, realtor=realtor)

    submit = await http_client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(),
        files=_photos(3),
        headers=auth_header(mint_token(realtor, "realtor")),
    )
    assert submit.status_code == 201, submit.text
    assert submit.json()["status"] == "completed"

    # Visible to the buyer, with presigned photo URLs.
    view = await http_client.get(
        f"/inspections/{inspection_id}/report", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["property_condition"] == "good"
    assert len(body["photo_urls"]) == 3


async def test_submit_gps_out_of_range_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    inspection_id = _seed_world(db_engine, buyer=buyer, seller=seller, realtor=realtor)

    resp = await http_client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(lat=_PROP_LAT + 1.0),  # ~111 km away
        files=_photos(3),
        headers=auth_header(mint_token(realtor, "realtor")),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "GPS_OUT_OF_RANGE"


async def test_submit_too_few_photos_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    inspection_id = _seed_world(db_engine, buyer=buyer, seller=seller, realtor=realtor)

    resp = await http_client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(),
        files=_photos(2),
        headers=auth_header(mint_token(realtor, "realtor")),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "MIN_PHOTOS_REQUIRED"


async def test_submit_by_non_assigned_realtor_is_403(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    inspection_id = _seed_world(db_engine, buyer=buyer, seller=seller, realtor=realtor)
    other = seed_user(role="realtor")

    resp = await http_client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(),
        files=_photos(3),
        headers=auth_header(mint_token(other, "realtor")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_ASSIGNED_REALTOR"


async def test_view_by_stranger_is_403(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    inspection_id = _seed_world(db_engine, buyer=buyer, seller=seller, realtor=realtor)
    await http_client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(),
        files=_photos(3),
        headers=auth_header(mint_token(realtor, "realtor")),
    )

    stranger = seed_user(role="buyer")
    resp = await http_client.get(
        f"/inspections/{inspection_id}/report", headers=auth_header(mint_token(stranger, "buyer"))
    )
    assert resp.status_code == 403
