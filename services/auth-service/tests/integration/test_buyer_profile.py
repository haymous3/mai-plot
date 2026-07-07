"""POST /auth/buyer/profile integration tests (SCRUM-132)."""

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
async def test_buyer_profile_persisted(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="buyer"
    )
    resp = await http_client.post(
        "/auth/buyer/profile",
        json={
            "employment_status": "self_employed",
            "preferred_location": "Lagos, Abuja",
            "budget_kobo": 4_000_000_000,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT employment_status, preferred_location, budget_kobo "
                "FROM buyer_profiles WHERE user_id = :id"
            ),
            {"id": user_id},
        ).first()
    assert row is not None
    assert row.employment_status == "self_employed"
    assert row.preferred_location == "Lagos, Abuja"
    assert row.budget_kobo == 4_000_000_000


@pytest.mark.asyncio
async def test_buyer_profile_partial_upsert_keeps_other_fields(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token, user_id = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="buyer"
    )
    first = await http_client.post(
        "/auth/buyer/profile",
        json={"employment_status": "employed", "budget_kobo": 100},
        headers=_auth(token),
    )
    assert first.status_code == 200
    # A later partial submit (only location) must not wipe the earlier values.
    second = await http_client.post(
        "/auth/buyer/profile", json={"preferred_location": "Ikeja"}, headers=_auth(token)
    )
    assert second.status_code == 200

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT employment_status, preferred_location, budget_kobo "
                "FROM buyer_profiles WHERE user_id = :id"
            ),
            {"id": user_id},
        ).first()
    assert row is not None
    assert row.employment_status == "employed"
    assert row.preferred_location == "Ikeja"
    assert row.budget_kobo == 100


@pytest.mark.asyncio
async def test_non_buyer_forbidden(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token, _ = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="seller"
    )
    resp = await http_client.post(
        "/auth/buyer/profile", json={"employment_status": "employed"}, headers=_auth(token)
    )
    assert resp.status_code == 403
    assert_error_envelope(resp.json(), "BUYER_ROLE_REQUIRED")


@pytest.mark.asyncio
async def test_invalid_employment_status_is_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token, _ = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", role="buyer"
    )
    resp = await http_client.post(
        "/auth/buyer/profile", json={"employment_status": "astronaut"}, headers=_auth(token)
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/buyer/profile", json={"employment_status": "employed"})
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
