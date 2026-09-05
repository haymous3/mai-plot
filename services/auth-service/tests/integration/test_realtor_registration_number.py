"""Realtor registration-number issuance + login integration tests (SCRUM-207).

Covers the internal issuance endpoint realtor-service calls at approval, and
the two-identifier login that follows from it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.twilio import InMemoryTwilioClient
from app.config import get_settings
from app.services.jwt_service import JwtService
from app.services.registration_number import normalize_registration_number
from tests.integration.conftest import assert_error_envelope, register_and_verify

_EMAIL = "realtor@example.com"
_PASSWORD = "SecurePass123!"
_PHONE = "08012345678"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for(role: str, db_engine: Engine, *, seed_user: bool = True) -> str:
    """Mint an access token for a seeded out-of-band account (admin accounts are
    provisioned, not registered)."""
    settings = get_settings()
    user_id = uuid4()
    if seed_user:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": user_id, "role": role},
            )
    jwt = JwtService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_expire_minutes=settings.jwt_access_expire_minutes,
        refresh_expire_days=settings.jwt_refresh_expire_days,
    )
    return jwt.issue_pair(user_id=user_id, role=role).access_token


async def _register_realtor(http_client: AsyncClient, sms: InMemoryTwilioClient) -> str:
    body = await register_and_verify(
        http_client, sms, phone=_PHONE, role="realtor", email=_EMAIL, password=_PASSWORD
    )
    user_id: str = body["user"]["id"]
    return user_id


async def _issue(http_client: AsyncClient, db_engine: Engine, user_id: str) -> dict[str, object]:
    admin = _token_for("admin", db_engine)
    response = await http_client.post(
        f"/internal/realtors/{user_id}/registration-number", headers=_auth(admin)
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


@pytest.mark.asyncio
async def test_issuance_returns_a_well_formed_number(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register_realtor(http_client, sms_fake)

    body = await _issue(http_client, db_engine, user_id)

    assert body["newly_issued"] is True
    number = body["registration_number"]
    assert isinstance(number, str)
    # The number Postgres minted must be one the login path recognises — this is
    # what keeps migration 0015's literal prefix and the Python module in step.
    assert normalize_registration_number(number) == number


@pytest.mark.asyncio
async def test_issuance_is_idempotent(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """An admin retrying a half-failed approval must not mint a second number:
    both would authenticate and only one was ever emailed."""
    user_id = await _register_realtor(http_client, sms_fake)

    first = await _issue(http_client, db_engine, user_id)
    second = await _issue(http_client, db_engine, user_id)

    assert second["registration_number"] == first["registration_number"]
    assert second["newly_issued"] is False

    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM realtor_registration_numbers WHERE user_id = :id"),
            {"id": user_id},
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_issuance_writes_one_audit_row(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register_realtor(http_client, sms_fake)
    await _issue(http_client, db_engine, user_id)
    await _issue(http_client, db_engine, user_id)  # no-op retry

    with db_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE action = 'realtor.registration_number_issued' AND entity_id = :id"
            ),
            {"id": user_id},
        ).scalar_one()
    assert rows == 1


@pytest.mark.asyncio
async def test_non_realtor_cannot_be_issued_a_number(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    body = await register_and_verify(
        http_client, sms_fake, phone=_PHONE, role="buyer", email="buyer@example.com"
    )
    admin = _token_for("admin", db_engine)

    response = await http_client.post(
        f"/internal/realtors/{body['user']['id']}/registration-number", headers=_auth(admin)
    )

    assert response.status_code == 422
    assert_error_envelope(response.json(), "NOT_REALTOR")


@pytest.mark.asyncio
async def test_unknown_user_is_404(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    admin = _token_for("admin", db_engine)
    response = await http_client.post(
        f"/internal/realtors/{uuid4()}/registration-number", headers=_auth(admin)
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "USER_NOT_FOUND")


@pytest.mark.asyncio
async def test_non_admin_is_forbidden(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """A realtor must not be able to issue their own number — that would let an
    unapproved application mint the credential approval is supposed to gate."""
    user_id = await _register_realtor(http_client, sms_fake)
    realtor_login = await http_client.post(
        "/auth/login", json={"identifier": _EMAIL, "password": _PASSWORD}
    )
    assert realtor_login.status_code == 200, realtor_login.text
    realtor_token = realtor_login.json()["access_token"]

    response = await http_client.post(
        f"/internal/realtors/{user_id}/registration-number", headers=_auth(realtor_token)
    )

    assert response.status_code == 403
    assert_error_envelope(response.json(), "ADMIN_FORBIDDEN")


@pytest.mark.asyncio
async def test_issuance_requires_a_token_at_all(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(f"/internal/realtors/{uuid4()}/registration-number")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_realtor_logs_in_with_the_issued_number(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register_realtor(http_client, sms_fake)
    number = (await _issue(http_client, db_engine, user_id))["registration_number"]

    response = await http_client.post(
        "/auth/login", json={"identifier": number, "password": _PASSWORD}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["id"] == user_id
    assert body["user"]["role"] == "realtor"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_approved_realtor_email_login_is_refused(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register_realtor(http_client, sms_fake)

    # Before issuance the email works — a pending application must stay reachable.
    before = await http_client.post(
        "/auth/login", json={"identifier": _EMAIL, "password": _PASSWORD}
    )
    assert before.status_code == 200, before.text

    await _issue(http_client, db_engine, user_id)

    after = await http_client.post(
        "/auth/login", json={"identifier": _EMAIL, "password": _PASSWORD}
    )
    assert after.status_code == 401
    # Same envelope as a wrong password: no way to learn this email belongs to
    # an approved realtor.
    assert_error_envelope(after.json(), "INVALID_CREDENTIALS")


@pytest.mark.asyncio
async def test_buyer_email_login_survives_the_identifier_change(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The legacy `email` field still authenticates — the admin sign-in proxy and
    any older client depend on it."""
    await register_and_verify(
        http_client,
        sms_fake,
        phone=_PHONE,
        role="buyer",
        email="buyer@example.com",
        password=_PASSWORD,
    )

    response = await http_client.post(
        "/auth/login", json={"email": "buyer@example.com", "password": _PASSWORD}
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_login_without_any_identifier_is_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post("/auth/login", json={"password": _PASSWORD})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_me_returns_the_registration_number(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register_realtor(http_client, sms_fake)

    login = await http_client.post(
        "/auth/login", json={"identifier": _EMAIL, "password": _PASSWORD}
    )
    token = login.json()["access_token"]
    before = await http_client.get("/auth/me", headers=_auth(token))
    assert before.status_code == 200, before.text
    # Pending: the portal shows "issued once verified", not a placeholder number.
    assert before.json()["registration_number"] is None

    number = (await _issue(http_client, db_engine, user_id))["registration_number"]

    after = await http_client.get("/auth/me", headers=_auth(token))
    assert after.status_code == 200, after.text
    assert after.json()["registration_number"] == number
