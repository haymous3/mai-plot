"""PoA review queue + decision integration tests (SCRUM-56)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.document_storage import InMemoryDocumentStorage
from app.adapters.email_verification import InMemoryEmailClient
from app.config import get_settings
from app.services.jwt_service import JwtService
from tests.integration.conftest import assert_error_envelope, register_and_verify

_PDF = b"%PDF-1.4\n1 0 obj power of attorney\nendobj"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _legal_team_token(db_engine: Engine) -> str:
    """Seed a legal_team user and mint a matching access token (legal_team
    users are provisioned out-of-band, not via /auth/register)."""
    settings = get_settings()
    user_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, role, verified_status, is_active) "
                "VALUES (:id, 'legal_team', 'id_verified', TRUE)"
            ),
            {"id": user_id},
        )
    jwt = JwtService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_expire_minutes=settings.jwt_access_expire_minutes,
        refresh_expire_days=settings.jwt_refresh_expire_days,
    )
    return jwt.issue_pair(user_id=user_id, role="legal_team").access_token


async def _seed_pending_poa_seller(
    http_client: AsyncClient, email_fake: InMemoryEmailClient, phone: str
) -> tuple[str, str]:
    """Register + verify a PoA seller and upload a PoA doc. Returns
    (user_id, seller_access_token); leaves poa_verified_status='pending'."""
    body = await register_and_verify(
        http_client,
        email_fake,
        phone=phone,
        role="seller",
        email=f"user{phone[-4:]}@maiplot.ng",
        seller_authority_type="power_of_attorney",
    )
    user_id = body["user"]["id"]
    token = body["access_token"]
    upload = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
        headers=_auth(token),
    )
    assert upload.status_code == 201, upload.text
    return user_id, token


@pytest.mark.asyncio
async def test_legal_team_sees_pending_submission_in_queue(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, _ = await _seed_pending_poa_seller(http_client, email_verification_fake, "08012345678")
    token = _legal_team_token(db_engine)

    response = await http_client.get("/admin/poa/queue", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["user_id"] == user_id


@pytest.mark.asyncio
async def test_non_legal_team_is_forbidden(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    _, seller_token = await _seed_pending_poa_seller(
        http_client, email_verification_fake, "08012345678"
    )
    response = await http_client.get("/admin/poa/queue", headers=_auth(seller_token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "LEGAL_TEAM_FORBIDDEN")


@pytest.mark.asyncio
async def test_queue_requires_authentication(
    clean_auth_tables: None,
    http_client: AsyncClient,
) -> None:
    response = await http_client.get("/admin/poa/queue")
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")


@pytest.mark.asyncio
async def test_approve_verifies_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, _ = await _seed_pending_poa_seller(http_client, email_verification_fake, "08012345678")
    token = _legal_team_token(db_engine)

    response = await http_client.post(
        f"/admin/poa/{user_id}/review", json={"action": "approve"}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["poa_verified_status"] == "verified"

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT poa_verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert row is not None and row.poa_verified_status == "verified"
        audit = conn.execute(
            text(
                "SELECT action, entity_type FROM audit_log "
                "WHERE entity_id = :id AND action = 'poa.verified'"
            ),
            {"id": user_id},
        ).first()
        assert audit is not None and audit.entity_type == "user"

    # The seller decision notification (in-app + SMS + email) is routed through
    # notification-service via notifications.dispatch — not auth-service's Termii.
    # Notifications are disabled in tests (no broker); the producer is covered in
    # the PoaReviewService unit tests.


@pytest.mark.asyncio
async def test_reject_without_reason_is_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, _ = await _seed_pending_poa_seller(http_client, email_verification_fake, "08012345678")
    token = _legal_team_token(db_engine)

    response = await http_client.post(
        f"/admin/poa/{user_id}/review", json={"action": "reject"}, headers=_auth(token)
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "POA_REASON_REQUIRED")

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT poa_verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert row is not None and row.poa_verified_status == "pending"  # unchanged


@pytest.mark.asyncio
async def test_reject_with_reason_sets_rejected(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, _ = await _seed_pending_poa_seller(http_client, email_verification_fake, "08012345678")
    token = _legal_team_token(db_engine)

    response = await http_client.post(
        f"/admin/poa/{user_id}/review",
        json={"action": "reject", "reason": "document is illegible"},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["poa_verified_status"] == "rejected"

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT poa_verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert row is not None and row.poa_verified_status == "rejected"


@pytest.mark.asyncio
async def test_review_already_decided_is_409(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, _ = await _seed_pending_poa_seller(http_client, email_verification_fake, "08012345678")
    token = _legal_team_token(db_engine)

    first = await http_client.post(
        f"/admin/poa/{user_id}/review", json={"action": "approve"}, headers=_auth(token)
    )
    assert first.status_code == 200
    second = await http_client.post(
        f"/admin/poa/{user_id}/review", json={"action": "approve"}, headers=_auth(token)
    )
    assert second.status_code == 409
    assert_error_envelope(second.json(), "POA_NOT_PENDING")


@pytest.mark.asyncio
async def test_review_unknown_user_is_404(
    clean_auth_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token = _legal_team_token(db_engine)
    response = await http_client.post(
        f"/admin/poa/{uuid4()}/review", json={"action": "approve"}, headers=_auth(token)
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "POA_TARGET_NOT_FOUND")
