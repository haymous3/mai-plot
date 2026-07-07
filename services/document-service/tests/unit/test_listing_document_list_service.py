"""Unit tests for ListingDocumentListService (SCRUM-95)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.document_repo import DocMetaRow
from app.services.listing_document_list import ListingDocumentListService

pytestmark = pytest.mark.asyncio


class _StubDocs:
    def __init__(self, rows: list[DocMetaRow]) -> None:
        self._rows = rows

    async def list_for_listing(self, listing_id: UUID) -> list[DocMetaRow]:
        return self._rows


async def test_maps_rows_to_meta() -> None:
    stub = _StubDocs(
        [
            DocMetaRow(document_type="c_of_o", verification_status="verified"),
            DocMetaRow(document_type="survey_plan", verification_status="pending"),
        ]
    )
    service = ListingDocumentListService(documents=stub)  # type: ignore[arg-type]
    resp = await service.list_for_listing(uuid4())

    assert [(d.document_type, d.verification_status) for d in resp.documents] == [
        ("c_of_o", "verified"),
        ("survey_plan", "pending"),
    ]


async def test_empty_when_no_documents() -> None:
    service = ListingDocumentListService(documents=_StubDocs([]))  # type: ignore[arg-type]
    resp = await service.list_for_listing(uuid4())
    assert resp.documents == []
