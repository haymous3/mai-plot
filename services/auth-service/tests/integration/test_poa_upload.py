"""POST /auth/poa/upload integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.document_storage import InMemoryDocumentStorage
from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope

_PDF = b"%PDF-1.4\n1 0 obj fake power of attorney document\nendobj"
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01 scanned poa"


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
    seller_authority_type: str | None = "power_of_attorney",
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
async def test_poa_upload_happy_path_for_power_of_attorney_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, token = await _register_verify_token(http_client, termii_fake, "08012345678")

    response = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["poa_verified_status"] == "pending"
    s3_key = body["s3_key"]
    assert s3_key.startswith(f"poa/{user_id}/")
    # The document bytes are never echoed back.
    assert "power of attorney" not in response.text

    # Stored in the (fake) private bucket.
    assert storage_fake.data[s3_key] == _PDF

    with db_engine.connect() as conn:
        pii = conn.execute(
            text("SELECT poa_document_s3_key FROM user_pii WHERE user_id = :id"),
            {"id": user_id},
        ).first()
        assert pii is not None and pii.poa_document_s3_key == s3_key

        user = conn.execute(
            text("SELECT poa_verified_status FROM users WHERE id = :id"), {"id": user_id}
        ).first()
        assert user is not None and user.poa_verified_status == "pending"

        audit = conn.execute(
            text(
                "SELECT action, entity_type, entity_id FROM audit_log "
                "WHERE entity_id = :id AND action = 'poa.uploaded'"
            ),
            {"id": user_id},
        ).first()
        assert audit is not None
        assert audit.entity_type == "user"


@pytest.mark.asyncio
async def test_poa_upload_accepts_jpeg(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    response = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.jpg", _JPEG, "image/jpeg")},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    assert response.json()["s3_key"].endswith(".jpg")


@pytest.mark.asyncio
async def test_poa_upload_rejects_owner_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(
        http_client, termii_fake, "08012345678", seller_authority_type="owner"
    )
    response = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
        headers=_auth(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "POA_NOT_ELIGIBLE")
    assert storage_fake.objects == {}


@pytest.mark.asyncio
async def test_poa_upload_rejects_buyer(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(
        http_client, termii_fake, "08012345678", role="buyer", seller_authority_type=None
    )
    response = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
        headers=_auth(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "POA_NOT_ELIGIBLE")


@pytest.mark.asyncio
async def test_poa_upload_rejects_non_pdf_jpeg(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    bad = b"GIF89a not an allowed legal document format"
    response = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.gif", bad, "image/gif")},
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "POA_DOCUMENT_INVALID")
    assert "legal document" not in response.text
    assert storage_fake.objects == {}


@pytest.mark.asyncio
async def test_poa_upload_twice_conflicts(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    _, token = await _register_verify_token(http_client, termii_fake, "08012345678")
    first = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
        headers=_auth(token),
    )
    assert first.status_code == 201

    second = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
        headers=_auth(token),
    )
    assert second.status_code == 409
    assert_error_envelope(second.json(), "POA_ALREADY_SUBMITTED")


@pytest.mark.asyncio
async def test_poa_upload_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    storage_fake: InMemoryDocumentStorage,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/poa/upload",
        files={"file": ("poa.pdf", _PDF, "application/pdf")},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
