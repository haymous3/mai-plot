"""OCR pipeline integration tests (SCRUM-55).

Drives the real upload endpoint. With ocr_via_celery default off, the upload
runs OCR inline against the fake engine (CI has no broker/AWS), so the
end-to-end effect — ocr_extracted_data populated, or the doc flagged for
manual review on failure — is observable in the DB right after the request.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_PDF = b"%PDF-1.4\nCertificate of Occupancy scan\n"


def _pdf() -> dict[str, Any]:
    return {"file": ("cofo.pdf", _PDF, "application/pdf")}


@pytest_asyncio.fixture
async def ocr_engine_fake() -> AsyncIterator[Any]:
    """Bind a controllable FakeOcrEngine (override the process-wide one) so a
    test can force the success or failure path deterministically."""
    from app.adapters.ocr import FakeOcrEngine
    from app.dependencies import get_ocr_engine
    from app.main import app

    fake = FakeOcrEngine()
    app.dependency_overrides[get_ocr_engine] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ocr_engine, None)


async def _upload(
    http_client: AsyncClient,
    listing_id: UUID,
    headers: dict[str, str],
) -> str:
    response = await http_client.post(
        f"/listings/{listing_id}/documents",
        files=_pdf(),
        data={"document_type": "c_of_o"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["document_id"])


def _row(db_engine: Engine, document_id: str) -> Any:
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT verification_status, ocr_extracted_data, verification_notes "
                "FROM listing_documents WHERE id = :id"
            ),
            {"id": document_id},
        ).first()


@pytest.mark.asyncio
async def test_upload_runs_ocr_and_stores_extracted_fields(
    clean_tables: None,
    doc_storage_fake: Any,
    ocr_engine_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    document_id = await _upload(http_client, listing_id, auth_header(token))

    row = _row(db_engine, document_id)
    assert row is not None
    # OCR success keeps the doc pending (a human still verifies) but populates
    # the extracted fields as JSONB.
    assert row.verification_status == "pending"
    data = row.ocr_extracted_data
    if isinstance(data, str):  # asyncpg may return JSONB as text
        data = json.loads(data)
    assert data["plot_number"] == "LA-1234"
    assert data["property_address"].startswith("12 Admiralty Way")


@pytest.mark.asyncio
async def test_ocr_failure_flags_document_for_manual_review(
    clean_tables: None,
    doc_storage_fake: Any,
    ocr_engine_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    ocr_engine_fake.fail_next = True  # force an engine failure on this upload
    document_id = await _upload(http_client, listing_id, auth_header(token))

    row = _row(db_engine, document_id)
    assert row is not None
    # Failure does not block the upload (201 above) but flags for manual review.
    assert row.verification_status == "under_review"
    assert row.verification_notes is not None
