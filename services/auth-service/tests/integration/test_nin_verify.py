"""POST /auth/verify/nin integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.nin import InMemoryNinVerifier
from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope

_NIN = "12345678901"


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


async def _register_verify_token(
    http_client: AsyncClient,
    termii_fake: InMemoryTermiiClient,
    phone: str,
    *,
    role: str = "seller",
    seller_authority_type: str | None = "owner",
) -> tuple[str, str]:
    """Register + OTP-verify a user; return (user_id, access_token)."""
    payload: dict[str, object] = {"phone": phone, "role": role}
    if seller_authority_type is not None:
        payload["seller_authority_type"] = seller_authority_type
    reg = await http_client.post("/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    user_id = reg.json()["user_id"]
    code = _extract_code(termii_fake.sent[-1].message)
    verify = await http_client.post(
        "/auth/otp/verify", json={"phone": phone, "otp": code, "purpose": "registration"}
    )
    assert verify.status_code == 200, verify.text
    return user_id, verify.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_nin_verify_happy_path_for_owner_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, token = await _register_verify_token(http_client, termii_fake, "08012345678")

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
    termii_fake: InMemoryTermiiClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(
        http_client, termii_fake, "08012345678", role="buyer", seller_authority_type=None
    )
    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "NIN_NOT_ELIGIBLE")
    assert nin_fake.calls == 0


@pytest.mark.asyncio
async def test_nin_verify_rejects_poa_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(
        http_client,
        termii_fake,
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
    termii_fake: InMemoryTermiiClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    first = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert first.status_code == 202

    second = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert second.status_code == 409
    assert_error_envelope(second.json(), "NIN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_nin_already_owned_by_another_account_conflicts(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token_a = await _register_verify_token(http_client, termii_fake, "08012345678")
    _, token_b = await _register_verify_token(http_client, termii_fake, "08087654321")

    first = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_a))
    assert first.status_code == 202

    second = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_b))
    assert second.status_code == 409
    assert_error_envelope(second.json(), "NIN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_nin_invalid_format_returns_422_without_echoing_value(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
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
