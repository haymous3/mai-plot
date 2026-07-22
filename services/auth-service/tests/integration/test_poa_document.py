"""PoA document serve endpoint integration tests (SCRUM-61)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.document_storage import InMemoryDocumentStorage
from app.adapters.email_verification import InMemoryEmailClient
from tests.integration.conftest import assert_error_envelope
from tests.integration.test_poa_review import (
    _PDF,
    _auth,
    _legal_team_token,
    _seed_pending_poa_seller,
)


@pytest.mark.asyncio
async def test_legal_team_can_view_poa_document(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, _ = await _seed_pending_poa_seller(http_client, email_verification_fake, "08012345678")
    token = _legal_team_token(db_engine)

    response = await http_client.get(f"/admin/poa/{user_id}/document", headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == _PDF

    # The access is audited (sensitive legal document).
    with db_engine.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE entity_id = :id AND action = 'poa.document_viewed'"
            ),
            {"id": user_id},
        ).first()
        assert audit is not None


@pytest.mark.asyncio
async def test_non_legal_team_cannot_view_document(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    user_id, seller_token = await _seed_pending_poa_seller(
        http_client, email_verification_fake, "08012345678"
    )
    response = await http_client.get(f"/admin/poa/{user_id}/document", headers=_auth(seller_token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "LEGAL_TEAM_FORBIDDEN")


@pytest.mark.asyncio
async def test_document_requires_authentication(
    clean_auth_tables: None,
    http_client: AsyncClient,
) -> None:
    response = await http_client.get(f"/admin/poa/{uuid4()}/document")
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")


@pytest.mark.asyncio
async def test_unknown_user_document_is_404(
    clean_auth_tables: None,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    token = _legal_team_token(db_engine)
    response = await http_client.get(f"/admin/poa/{uuid4()}/document", headers=_auth(token))
    assert response.status_code == 404
    assert_error_envelope(response.json(), "POA_DOCUMENT_NOT_FOUND")
