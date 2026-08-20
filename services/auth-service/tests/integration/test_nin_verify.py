"""POST /auth/verify/nin integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.nin import InMemoryNinVerifier
from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

_NIN = "12345678901"


async def _register_verify_token(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    phone: str,
    *,
    role: str = "seller",
    seller_authority_type: str | None = "owner",
    email: str = "seller@example.com",
) -> tuple[str, str]:
    """Register + email-verify a user; return (user_id, access_token)."""
    body = await register_and_verify(
        http_client,
        sms,
        phone=phone,
        role=role,
        email=email,
        seller_authority_type=seller_authority_type,
    )
    return body["user"]["id"], body["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_nin_verify_happy_path_for_owner_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, token = await _register_verify_token(http_client, sms_fake, "08012345678")

    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "verified"
    assert _NIN not in response.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT nin_hash, nin_lookup FROM user_pii WHERE user_id = :id"),
            {"id": user_id},
        ).first()
        assert row is not None
        assert row.nin_hash is not None and row.nin_hash != _NIN
        assert row.nin_hash.startswith("$2")
        assert row.nin_lookup is not None and len(row.nin_lookup) == 64

        status_row = conn.execute(
            text("SELECT verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert status_row is not None
        assert status_row.verified_status == "id_verified"


@pytest.mark.asyncio
async def test_nin_verify_rejects_buyer(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(
        http_client,
        sms_fake,
        "08012345678",
        role="buyer",
        seller_authority_type=None,
    )
    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "NIN_NOT_ELIGIBLE")
    assert nin_fake.calls == 0


@pytest.mark.asyncio
async def test_nin_verify_rejects_poa_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(
        http_client,
        sms_fake,
        "08012345678",
        role="seller",
        seller_authority_type="power_of_attorney",
    )
    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "NIN_NOT_ELIGIBLE")


@pytest.mark.asyncio
async def test_nin_verify_same_user_twice_conflicts(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, sms_fake, "08012345678")
    first = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert first.status_code == 202

    second = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert second.status_code == 409
    assert_error_envelope(second.json(), "NIN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_nin_already_owned_by_another_account_conflicts(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token_a = await _register_verify_token(http_client, sms_fake, "08012345678")
    _, token_b = await _register_verify_token(
        http_client, sms_fake, "08087654321", email="second@example.com"
    )

    first = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_a))
    assert first.status_code == 202

    second = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_b))
    assert second.status_code == 409
    assert_error_envelope(second.json(), "NIN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_nin_invalid_format_returns_422_without_echoing_value(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, sms_fake, "08012345678")
    bad = "999abc"
    response = await http_client.post("/auth/verify/nin", json={"nin": bad}, headers=_auth(token))
    assert response.status_code == 422
    assert_error_envelope(response.json(), "NIN_FORMAT_INVALID")
    assert bad not in response.text


@pytest.mark.asyncio
async def test_nin_verify_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN})
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
