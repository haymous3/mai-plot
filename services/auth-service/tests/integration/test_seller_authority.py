"""POST /auth/seller/authority integration tests (SCRUM-132)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.email_verification import InMemoryEmailClient
from tests.integration.conftest import assert_error_envelope, register_and_verify


async def _register_verify_token(
    http_client: AsyncClient,
    email_fake: InMemoryEmailClient,
    *,
    phone: str,
    role: str,
) -> tuple[str, str]:
    """Register + email-verify a user; return (access_token, user_id)."""
    body = await register_and_verify(
        http_client, email_fake, phone=phone, role=role, email=f"user{phone[-4:]}@maiplot.ng"
    )
    return body["access_token"], body["user"]["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_poa_seller_enters_pending_queue(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, email_verification_fake, phone="08012345678", role="seller"
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
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, email_verification_fake, phone="08012345678", role="seller"
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
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    token, _ = await _register_verify_token(
        http_client, email_verification_fake, phone="08012345678", role="buyer"
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
