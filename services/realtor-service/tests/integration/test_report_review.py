"""Integration tests for admin inspection-report review (SCRUM-205)."""

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
    """Listing + transaction + an accepted inspection confirmed in the past, so
    a report can be submitted straight away. Returns the inspection id."""
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


def _form() -> dict[str, object]:
    return {
        "gps_lat": str(_PROP_LAT),
        "gps_lng": str(_PROP_LNG),
        "property_condition": "good",
        "remarks": "Looks fine",
    }


async def _submit(client: AsyncClient, inspection_id: UUID, headers: dict[str, str]) -> None:
    resp = await client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(),
        files=_photos(),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


# -- the queue --------------------------------------------------------------


async def test_queue_requires_admin(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    assert (await http_client.get("/admin/inspections/reports/queue")).status_code == 401
    realtor = seed_user(role="realtor")
    forbidden = await http_client.get(
        "/admin/inspections/reports/queue",
        headers=auth_header(mint_token(realtor, "realtor")),
    )
    assert forbidden.status_code == 403


async def test_submitted_report_lands_in_the_queue_as_pending(
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
    await _submit(http_client, inspection_id, auth_header(mint_token(realtor, "realtor")))

    resp = await http_client.get(
        "/admin/inspections/reports/queue",
        headers=auth_header(mint_token(seed_user(role="admin"), "admin")),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) == 1
    assert items[0]["inspection_id"] == str(inspection_id)
    assert items[0]["report_review_status"] == "pending"
    assert items[0]["report_revision"] == 1
    assert items[0]["property_title"] == "Plot"
    # §10: the realtor is identity only — no contact details in the queue.
    assert "phone" not in resp.text and "email" not in resp.text


# -- decisions --------------------------------------------------------------


async def test_approve_moves_it_out_of_the_pending_queue(
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
    await _submit(http_client, inspection_id, auth_header(mint_token(realtor, "realtor")))
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    decided = await http_client.post(
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "approve"},
        headers=admin_headers,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["report_review_status"] == "approved"

    pending = await http_client.get("/admin/inspections/reports/queue", headers=admin_headers)
    assert pending.json()["data"] == []

    everything = await http_client.get(
        "/admin/inspections/reports/queue?review_status=all", headers=admin_headers
    )
    assert everything.json()["data"][0]["report_review_status"] == "approved"


async def test_reject_without_a_note_is_422(
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
    await _submit(http_client, inspection_id, auth_header(mint_token(realtor, "realtor")))

    resp = await http_client.post(
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "reject", "note": "  "},
        headers=auth_header(mint_token(seed_user(role="admin"), "admin")),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "REVIEW_NOTE_REQUIRED"


async def test_deciding_twice_is_a_conflict(
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
    await _submit(http_client, inspection_id, auth_header(mint_token(realtor, "realtor")))
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    first = await http_client.post(
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "approve"},
        headers=admin_headers,
    )
    assert first.status_code == 200

    second = await http_client.post(
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "reject", "note": "changed my mind"},
        headers=admin_headers,
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "REPORT_NOT_PENDING"


async def test_reviewing_an_unsubmitted_report_is_404(
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
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "approve"},
        headers=auth_header(mint_token(seed_user(role="admin"), "admin")),
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "REPORT_NOT_FOUND"


# -- resubmission -----------------------------------------------------------


async def test_rejected_report_can_be_resubmitted_and_returns_to_the_queue(
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
    realtor_headers = auth_header(mint_token(realtor, "realtor"))
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    await _submit(http_client, inspection_id, realtor_headers)
    rejected = await http_client.post(
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "reject", "note": "Photos too dark."},
        headers=admin_headers,
    )
    assert rejected.status_code == 200

    # The realtor sees the rejection and the reason on their own read.
    mine = await http_client.get("/inspections/mine", headers=realtor_headers)
    item = mine.json()["data"][0]
    assert item["report_review_status"] == "rejected"
    assert item["report_review_note"] == "Photos too dark."

    # And can resubmit, even though the inspection is still 'completed'.
    await _submit(http_client, inspection_id, realtor_headers)

    requeued = await http_client.get("/admin/inspections/reports/queue", headers=admin_headers)
    row = requeued.json()["data"][0]
    assert row["report_review_status"] == "pending"
    assert row["report_revision"] == 2
    # The rejection note is cleared — it belonged to the superseded revision.
    assert row["report_review_note"] is None


async def test_approved_report_cannot_be_resubmitted(
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
    realtor_headers = auth_header(mint_token(realtor, "realtor"))

    await _submit(http_client, inspection_id, realtor_headers)
    await http_client.post(
        f"/admin/inspections/{inspection_id}/report/review",
        json={"action": "approve"},
        headers=auth_header(mint_token(seed_user(role="admin"), "admin")),
    )

    resp = await http_client.post(
        f"/inspections/{inspection_id}/report",
        data=_form(),
        files=_photos(),
        headers=realtor_headers,
    )
    # 409, matching the pre-existing mapping for a report that cannot be filed.
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "REPORT_NOT_SUBMITTABLE"


async def test_review_is_not_a_visibility_gate_for_the_buyer(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Product decision: buyer and seller read any submitted report, reviewed or
    not. A report must not go dark between submission and review."""
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    inspection_id = _seed_world(db_engine, buyer=buyer, seller=seller, realtor=realtor)
    await _submit(http_client, inspection_id, auth_header(mint_token(realtor, "realtor")))

    seen = await http_client.get(
        f"/inspections/{inspection_id}/report",
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert seen.status_code == 200, seen.text
    assert seen.json()["property_condition"] == "good"
