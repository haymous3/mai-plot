"""POST /auth/seller/authority integration tests (SCRUM-132)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


async def _register_verify_token(
    http_client: AsyncClient,
    termii_fake: InMemoryTermiiClient,
    *,
    phone: str,
    role: str,
) -> tuple[str, str]:
    reg = await http_client.post("/auth/register", json={"phone": phone, "role": role})
    assert reg.status_code == 201, reg.text
    user_id: str = reg.json()["user_id"]
    code = _extract_code(termii_fake.sent[-1].message)
    verify = await http_client.post(
        "/auth/otp/verify", json={"phone": phone, "otp": code, "purpose": "registration"}
    )
    assert verify.status_code == 200, verify.text
    return verify.json()["access_token"], user_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_poa_seller_enters_pending_queue(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="seller"
    )
    resp = await http_client.post(
        "/auth/seller/authority",
        json={"authority_type": "power_of_attorney"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["authority_type"] == "power_of_attorney"

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT seller_authority_type, poa_verified_status FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
    assert row is not None
    assert row.seller_authority_type == "power_of_attorney"
    assert row.poa_verified_status == "pending"


@pytest.mark.asyncio
async def test_owner_seller_is_not_applicable(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="seller"
    )
    resp = await http_client.post(
        "/auth/seller/authority", json={"authority_type": "owner"}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT seller_authority_type, poa_verified_status FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
    assert row is not None
    assert row.seller_authority_type == "owner"
    assert row.poa_verified_status == "not_applicable"


@pytest.mark.asyncio
async def test_non_seller_forbidden(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token, _ = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="buyer"
    )
    resp = await http_client.post(
        "/auth/seller/authority", json={"authority_type": "owner"}, headers=_auth(token)
    )
    assert resp.status_code == 403
    assert_error_envelope(resp.json(), "SELLER_ROLE_REQUIRED")


@pytest.mark.asyncio
async def test_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/seller/authority", json={"authority_type": "owner"})
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
