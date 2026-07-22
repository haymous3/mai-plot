"""GET /auth/seller/poa-status integration tests (SCRUM-137)."""

from __future__ import annotations

import json

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
async def test_poa_seller_pending_blocks_publish(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    token, _ = await _register_verify_token(
        http_client, email_verification_fake, phone="08012345678", role="seller"
    )
    await http_client.post(
        "/auth/seller/authority",
        json={"authority_type": "power_of_attorney"},
        headers=_auth(token),
    )

    resp = await http_client.get("/auth/seller/poa-status", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["authority_type"] == "power_of_attorney"
    assert body["status"] == "pending"
    assert body["can_publish"] is False
    assert body["rejection_reason"] is None


@pytest.mark.asyncio
async def test_owner_can_publish(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    token, _ = await _register_verify_token(
        http_client, email_verification_fake, phone="08012345678", role="seller"
    )
    await http_client.post(
        "/auth/seller/authority", json={"authority_type": "owner"}, headers=_auth(token)
    )

    resp = await http_client.get("/auth/seller/poa-status", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["authority_type"] == "owner"
    assert body["status"] == "not_applicable"
    assert body["can_publish"] is True


@pytest.mark.asyncio
async def test_rejected_surfaces_reason_from_audit_log(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, email_verification_fake, phone="08012345678", role="seller"
    )
    await http_client.post(
        "/auth/seller/authority",
        json={"authority_type": "power_of_attorney"},
        headers=_auth(token),
    )

    # Simulate a legal-team rejection: status -> rejected + the audit trail entry
    # the reason is read from (mirrors PoaReviewService's write).
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET poa_verified_status = 'rejected' WHERE id = :id"),
            {"id": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO audit_log (action, entity_type, entity_id, new_value) "
                "VALUES ('poa.rejected', 'user', :id, CAST(:nv AS jsonb))"
            ),
            {
                "id": user_id,
                "nv": json.dumps({"poa_verified_status": "rejected", "reason": "blurry scan"}),
            },
        )

    resp = await http_client.get("/auth/seller/poa-status", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["can_publish"] is False
    assert body["rejection_reason"] == "blurry scan"


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
    resp = await http_client.get("/auth/seller/poa-status", headers=_auth(token))
    assert resp.status_code == 403
    assert_error_envelope(resp.json(), "SELLER_ROLE_REQUIRED")


@pytest.mark.asyncio
async def test_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.get("/auth/seller/poa-status")
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
