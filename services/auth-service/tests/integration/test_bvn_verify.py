"""POST /auth/verify/bvn integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.bvn import BvnVerificationOutcome, InMemoryBvnVerifier
from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope

_BVN = "12345678901"


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


async def _register_verify_token(
    http_client: AsyncClient, termii_fake: InMemoryTermiiClient, phone: str
) -> tuple[str, str]:
    """Register + OTP-verify a user; return (user_id, access_token)."""
    reg = await http_client.post("/auth/register", json={"phone": phone, "role": "buyer"})
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
async def test_bvn_verify_happy_path(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    bvn_fake: InMemoryBvnVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, token = await _register_verify_token(http_client, termii_fake, "08012345678")

    response = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN}, headers=_auth(token))

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "verified"
    # The BVN must never appear in the response body.
    assert _BVN not in response.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT bvn_hash, bvn_lookup FROM user_pii WHERE user_id = :id"),
            {"id": user_id},
        ).first()
        assert row is not None
        # Stored as a bcrypt hash + an HMAC lookup, never the raw BVN.
        assert row.bvn_hash is not None and row.bvn_hash != _BVN
        assert row.bvn_hash.startswith("$2")
        assert row.bvn_lookup is not None and row.bvn_lookup != _BVN
        assert len(row.bvn_lookup) == 64

        status_row = conn.execute(
            text("SELECT verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert status_row is not None
        assert status_row.verified_status == "id_verified"


@pytest.mark.asyncio
async def test_bvn_verify_same_user_twice_conflicts(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    bvn_fake: InMemoryBvnVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    first = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN}, headers=_auth(token))
    assert first.status_code == 202

    second = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN}, headers=_auth(token))
    assert second.status_code == 409
    assert_error_envelope(second.json(), "BVN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_bvn_already_owned_by_another_account_conflicts(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    bvn_fake: InMemoryBvnVerifier,
    http_client: AsyncClient,
) -> None:
    _, token_a = await _register_verify_token(http_client, termii_fake, "08012345678")
    _, token_b = await _register_verify_token(http_client, termii_fake, "08087654321")

    first = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN}, headers=_auth(token_a))
    assert first.status_code == 202

    # Second account submitting the same BVN is rejected by the unique lookup.
    second = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN}, headers=_auth(token_b))
    assert second.status_code == 409
    assert_error_envelope(second.json(), "BVN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_bvn_invalid_format_returns_422_without_echoing_value(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    bvn_fake: InMemoryBvnVerifier,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    bad = "123abc"
    response = await http_client.post("/auth/verify/bvn", json={"bvn": bad}, headers=_auth(token))
    assert response.status_code == 422
    assert_error_envelope(response.json(), "BVN_FORMAT_INVALID")
    # The bad value is not reflected back.
    assert bad not in response.text


@pytest.mark.asyncio
async def test_bvn_verify_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    bvn_fake: InMemoryBvnVerifier,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN})
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")


@pytest.mark.asyncio
async def test_bvn_not_verified_result_keeps_status_unchanged(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    bvn_fake: InMemoryBvnVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    bvn_fake.outcome = BvnVerificationOutcome(status="failed")

    response = await http_client.post("/auth/verify/bvn", json={"bvn": _BVN}, headers=_auth(token))
    assert response.status_code == 202
    assert response.json()["status"] == "failed"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT bvn_hash, verified_status FROM user_pii "
                "JOIN users ON users.id = user_pii.user_id WHERE user_pii.user_id = :id"
            ),
            {"id": user_id},
        ).first()
        assert row is not None
        # A failed verification stores nothing and does not advance status.
        assert row.bvn_hash is None
        assert row.verified_status == "phone_verified"
