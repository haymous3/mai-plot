"""POST /auth/verify/nin integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.nin import InMemoryNinVerifier, NinVerificationOutcome
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
async def test_nin_verify_accepts_a_buyer(
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
    # SCRUM-189: this used to be a hard 403 NIN_NOT_ELIGIBLE, which is why
    # buyer onboarding collected a BVN instead. NIN is now the platform-wide
    # identity check, so every role may verify their own.
    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert response.status_code == 202
    assert nin_fake.calls == 1


@pytest.mark.asyncio
async def test_nin_verify_accepts_a_poa_seller(
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
    # This was a live bug, not just a limitation: seller onboarding already
    # asked every seller for a NIN, so a PoA seller was 403'd on a step the
    # funnel required of them.
    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    assert response.status_code == 202


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


@pytest.mark.asyncio
async def test_rejected_nin_returns_422_not_202(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """SCRUM-218. This route used to answer 202 for EVERY outcome, and every
    frontend checks only `resp.ok` — so a NIN the registry rejected walked
    through onboarding looking verified. Nothing may be persisted either."""
    user_id, token = await _register_verify_token(http_client, sms_fake, "08012345678")
    nin_fake.outcome = NinVerificationOutcome(status="failed", mismatches=("last_name",))

    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))

    assert response.status_code == 422
    assert_error_envelope(response.json(), "NIN_NOT_VERIFIED")
    assert response.json()["details"]["mismatches"] == ["last_name"]
    assert _NIN not in response.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT nin_hash FROM user_pii WHERE user_id = :id"), {"id": user_id}
        ).first()
        assert row is not None and row.nin_hash is None
        status_row = conn.execute(
            text("SELECT verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert status_row is not None
        assert status_row.verified_status != "id_verified"


@pytest.mark.asyncio
async def test_review_outcome_is_202_pending_but_not_id_verified(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """A partial name match is not a fraud signal, so onboarding continues —
    but the account must not be advanced on the strength of it."""
    user_id, token = await _register_verify_token(http_client, sms_fake, "08012345678")
    nin_fake.outcome = NinVerificationOutcome(status="pending", mismatches=("last_name",))

    response = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["mismatches"] == ["last_name"]

    with db_engine.connect() as conn:
        status_row = conn.execute(
            text("SELECT verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert status_row is not None
        assert status_row.verified_status != "id_verified"


@pytest.mark.asyncio
async def test_submitted_name_is_forwarded_to_the_registry(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    """Onboarding verifies the NIN before it writes the profile, so it sends
    the name alongside — otherwise there would be nothing to match against."""
    _, token = await _register_verify_token(http_client, sms_fake, "08012345678")

    response = await http_client.post(
        "/auth/verify/nin",
        json={"nin": _NIN, "first_name": "Adaeze", "last_name": "Okonkwo"},
        headers=_auth(token),
    )

    assert response.status_code == 202, response.text
    assert nin_fake.last_first_name == "Adaeze"
    assert nin_fake.last_last_name == "Okonkwo"


@pytest.mark.asyncio
async def test_deleting_an_account_releases_its_nin(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    """SCRUM-227, reported from the live funnel: verify a NIN, delete the
    account, then sign up again with the same NIN.

    This used to answer 409 forever — the soft-deleted row kept the NIN
    reserved, and nobody gets a new NIN, so deleting an account locked that
    person out of the platform permanently. Migration 0018 scopes both the
    index and the lookup to live rows.
    """
    _, token_a = await _register_verify_token(http_client, sms_fake, "08012345678")
    first = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_a))
    assert first.status_code == 202, first.text

    deleted = await http_client.post("/auth/account/delete", headers=_auth(token_a))
    assert deleted.status_code == 200, deleted.text

    # A brand-new account, same human, same NIN.
    _, token_b = await _register_verify_token(
        http_client, sms_fake, "08087654321", email="again@example.com"
    )
    second = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_b))

    assert second.status_code == 202, second.text


@pytest.mark.asyncio
async def test_a_live_account_still_blocks_its_nin(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    """The other half of SCRUM-227: releasing on delete must not weaken the
    guard while the account is alive. One LIVE account per NIN is the whole
    invariant the unique index exists for."""
    _, token_a = await _register_verify_token(http_client, sms_fake, "08012345678")
    assert (
        await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_a))
    ).status_code == 202

    _, token_b = await _register_verify_token(
        http_client, sms_fake, "08087654321", email="second@example.com"
    )
    second = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token_b))

    assert second.status_code == 409
    assert_error_envelope(second.json(), "NIN_ALREADY_VERIFIED")


@pytest.mark.asyncio
async def test_the_deleted_accounts_hashes_are_kept(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """Only the RESERVATION is released. The hashes stay on the dead row —
    AMLON/KYC history must survive a user deleting their account."""
    user_id, token = await _register_verify_token(http_client, sms_fake, "08012345678")
    await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(token))
    await http_client.post("/auth/account/delete", headers=_auth(token))

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT nin_hash, nin_lookup, deleted_at FROM user_pii WHERE user_id = :id"),
            {"id": user_id},
        ).first()
        assert row is not None
        assert row.nin_hash is not None
        assert row.nin_lookup is not None
        # The trigger from migration 0009 is what makes the partial index work.
        assert row.deleted_at is not None
