"""POST /auth/register integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope


@pytest.mark.asyncio
async def test_register_buyer_happy_path(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "user_id" in body
    assert body["otp_expires_in_seconds"] == 300
    assert "+2348012345678" in body["message"]

    # X-Trace-ID middleware echoes the generated value back.
    assert response.headers.get("X-Trace-ID")

    # User and OTP were persisted.
    with db_engine.connect() as conn:
        user_row = conn.execute(
            text("SELECT id, role, verified_status FROM users WHERE id = :id"),
            {"id": body["user_id"]},
        ).first()
        assert user_row is not None
        assert user_row.role == "buyer"
        assert user_row.verified_status == "unverified"

        pii_row = conn.execute(
            text("SELECT phone FROM user_pii WHERE user_id = :id"),
            {"id": body["user_id"]},
        ).first()
        assert pii_row is not None
        assert pii_row.phone == "+2348012345678"

        otp_count = conn.execute(
            text(
                "SELECT count(*) FROM otp_codes "
                "WHERE phone = :p AND purpose = 'registration' AND used_at IS NULL"
            ),
            {"p": "+2348012345678"},
        ).scalar_one()
        assert otp_count == 1

    # Termii fake received one SMS containing a 6-digit code.
    assert len(termii_fake.sent) == 1
    sent = termii_fake.sent[0]
    assert sent.phone == "+2348012345678"
    assert any(
        part.rstrip(".").isdigit() and len(part.rstrip(".")) == 6 for part in sent.message.split()
    )


@pytest.mark.asyncio
async def test_register_seller_requires_authority_type(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "seller"},
    )

    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")
    assert termii_fake.sent == []


@pytest.mark.asyncio
async def test_register_seller_with_authority_type_succeeds(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={
            "phone": "08012345678",
            "role": "seller",
            "seller_authority_type": "power_of_attorney",
        },
    )

    assert response.status_code == 201
    body = response.json()
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT seller_authority_type, poa_verified_status FROM users WHERE id = :id"),
            {"id": body["user_id"]},
        ).first()
        assert row is not None
        assert row.seller_authority_type == "power_of_attorney"
        # PoA holders enter the pending review queue automatically.
        assert row.poa_verified_status == "pending"


@pytest.mark.asyncio
async def test_register_duplicate_phone_returns_400(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    body = {"phone": "08012345678", "role": "buyer"}
    first = await http_client.post("/auth/register", json=body)
    assert first.status_code == 201

    second = await http_client.post("/auth/register", json=body)
    assert second.status_code == 400
    assert_error_envelope(second.json(), "PHONE_ALREADY_REGISTERED")
    # The fake captured only the first registration's SMS.
    assert len(termii_fake.sent) == 1


@pytest.mark.asyncio
async def test_register_invalid_role_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "bank_partner"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_register_invalid_phone_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "+15551234567", "role": "buyer"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_register_trace_id_is_echoed(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    trace_id = "550e8400-e29b-41d4-a716-446655440000"
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer"},
        headers={"X-Trace-ID": trace_id},
    )
    assert response.status_code == 201
    assert response.headers["X-Trace-ID"] == trace_id
