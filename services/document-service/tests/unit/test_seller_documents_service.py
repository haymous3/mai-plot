"""Unit tests for SellerDocumentsService (SCRUM-98)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.document_repo import SellerDocRow
from app.services.seller_documents import SellerDocumentsService

pytestmark = pytest.mark.asyncio


class _StubDocs:
    def __init__(self, rows: list[SellerDocRow]) -> None:
        self._rows = rows
        self.seen: UUID | None = None

    async def list_for_seller(self, seller_id: UUID) -> list[SellerDocRow]:
        self.seen = seller_id
        return self._rows


async def test_maps_rows_including_admin_feedback() -> None:
    seller = uuid4()
    row = SellerDocRow(
        id=uuid4(),
        listing_id=uuid4(),
        property_title="Luxury Villa",
        document_type="deed_of_assignment",
        verification_status="failed",
        verification_notes="Document quality is poor. Please re-upload a clearer scan.",
        created_at=datetime.now(UTC),
    )
    repo = _StubDocs([row])
    resp = await SellerDocumentsService(documents=repo).list_for_seller(seller)  # type: ignore[arg-type]

    assert repo.seen == seller
    item = resp.data[0]
    assert item.document_type == "deed_of_assignment"
    assert item.verification_status == "failed"
    assert item.verification_notes is not None
    assert item.verification_notes.startswith("Document quality")


async def test_empty() -> None:
    resp = await SellerDocumentsService(documents=_StubDocs([])).list_for_seller(uuid4())  # type: ignore[arg-type]
    assert resp.data == []
