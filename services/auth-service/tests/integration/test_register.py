"""POST /auth/register integration tests (phone-OTP flow, SCRUM-175).

SCRUM-175 reverted the verification channel from the SCRUM-152 email magic
link to phone OTP over SMS. Register now persists an otp_codes row and
dispatches an SMS; it no longer mints an email_verification_tokens row.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, extract_otp_code

_EMAIL = "buyer@example.com"


@pytest.mark.asyncio
async def test_register_buyer_happy_path(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": _EMAIL, "full_name": "Ada Obi"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "user_id" in body
    # Now the OTP TTL (5 min), not the magic-link TTL (30 min).
    assert body["verification_expires_in_seconds"] == 5 * 60
    assert "08012345678" in body["message"]

    # X-Trace-ID middleware echoes the generated value back.
    assert response.headers.get("X-Trace-ID")

    # User and verification token were persisted.
    with db_engine.connect() as conn:
        user_row = conn.execute(
            text("SELECT id, role, verified_status, email FROM users WHERE id = :id"),
            {"id": body["user_id"]},
        ).first()
        assert user_row is not None
        assert user_row.role == "buyer"
        assert user_row.verified_status == "unverified"
        assert user_row.email == _EMAIL

        pii_row = conn.execute(
            text("SELECT phone, full_name FROM user_pii WHERE user_id = :id"),
            {"id": body["user_id"]},
        ).first()
        assert pii_row is not None
        assert pii_row.phone == "+2348012345678"
        assert pii_row.full_name == "Ada Obi"

        otp_count = conn.execute(
            text(
                "SELECT count(*) FROM otp_codes "
                "WHERE phone = '+2348012345678' AND purpose = 'registration' "
                "AND used_at IS NULL"
            ),
        ).scalar_one()
        assert otp_count == 1

        # No magic link is minted any more.
        token_count = conn.execute(
            text("SELECT count(*) FROM email_verification_tokens WHERE user_id = :id"),
            {"id": body["user_id"]},
        ).scalar_one()
        assert token_count == 0

    # The SMS fake captured one message carrying a 6-digit code.
    assert len(sms_fake.sent) == 1
    sent = sms_fake.sent[0]
    assert sent.phone == "+2348012345678"
    assert extract_otp_code(sent.message)


@pytest.mark.asyncio
async def test_register_normalises_email_case(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": "  Buyer@Example.COM "},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    with db_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT email FROM users WHERE id = :id"), {"id": body["user_id"]}
        ).scalar_one()
    assert stored == "buyer@example.com"


@pytest.mark.asyncio
async def test_register_seller_without_authority_is_allowed(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    # SCRUM-132: authority is declared later on the Seller Verification screen,
    # so a seller may register without it (and still gets a verification SMS).
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "seller", "email": "seller@example.com"},
    )

    assert response.status_code == 201, response.text
    assert len(sms_fake.sent) == 1


@pytest.mark.asyncio
async def test_register_seller_with_authority_type_succeeds(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={
            "phone": "08012345678",
            "role": "seller",
            "email": "seller@example.com",
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
async def test_register_duplicate_email_returns_400(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    first = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": _EMAIL},
    )
    assert first.status_code == 201

    # Same email, different phone -> rejected on email uniqueness.
    second = await http_client.post(
        "/auth/register",
        json={"phone": "08087654321", "role": "buyer", "email": _EMAIL},
    )
    assert second.status_code == 400
    assert_error_envelope(second.json(), "EMAIL_ALREADY_REGISTERED")
    # The fake captured only the first registration's SMS.
    assert len(sms_fake.sent) == 1


@pytest.mark.asyncio
async def test_register_duplicate_phone_returns_400(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    first = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": _EMAIL},
    )
    assert first.status_code == 201

    # Same phone, different email -> rejected on phone uniqueness.
    second = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": "other@example.com"},
    )
    assert second.status_code == 400
    assert_error_envelope(second.json(), "PHONE_ALREADY_REGISTERED")
    assert len(sms_fake.sent) == 1


@pytest.mark.asyncio
async def test_register_missing_email_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": "not-an-email"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_register_invalid_role_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "bank_partner", "email": _EMAIL},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_register_invalid_phone_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/register",
        json={"phone": "+15551234567", "role": "buyer", "email": _EMAIL},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_register_trace_id_is_echoed(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    trace_id = "550e8400-e29b-41d4-a716-446655440000"
    response = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": _EMAIL},
        headers={"X-Trace-ID": trace_id},
    )
    assert response.status_code == 201
    assert response.headers["X-Trace-ID"] == trace_id
