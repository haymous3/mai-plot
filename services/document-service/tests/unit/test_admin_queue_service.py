"""AdminQueueService — source dispatch, field mapping, pagination maths.

The service had no unit test before SCRUM-192; it was a thin pass-through to
one repository. Now that it fans out to two tables with different columns, the
mapping is worth pinning down.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.document_repo import QueueRow
from app.repositories.user_document_repo import UserDocQueueRow
from app.services.admin_queue import AdminQueueService

_NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


class _StubListingRepo:
    def __init__(self, rows: list[QueueRow], total: int | None = None) -> None:
        self._rows = rows
        self._total = total if total is not None else len(rows)
        self.calls: list[dict[str, object]] = []

    async def list_queue(
        self, *, status: str, page: int, page_size: int
    ) -> tuple[list[QueueRow], int]:
        self.calls.append({"status": status, "page": page, "page_size": page_size})
        return self._rows, self._total


class _StubUserRepo:
    def __init__(self, rows: list[UserDocQueueRow], total: int | None = None) -> None:
        self._rows = rows
        self._total = total if total is not None else len(rows)
        self.calls: list[dict[str, object]] = []

    async def list_queue(
        self, *, status: str, page: int, page_size: int
    ) -> tuple[list[UserDocQueueRow], int]:
        self.calls.append({"status": status, "page": page, "page_size": page_size})
        return self._rows, self._total


def _listing_row() -> QueueRow:
    return QueueRow(
        id=uuid4(),
        listing_id=uuid4(),
        document_type="c_of_o",
        verification_status="pending",
        created_at=_NOW,
    )


def _personal_row(owner_name: str | None = "Ada Obi") -> UserDocQueueRow:
    return UserDocQueueRow(
        id=uuid4(),
        user_id=uuid4(),
        owner_name=owner_name,
        category="identity",
        file_name="nin-slip.pdf",
        size_bytes=2048,
        content_type="application/pdf",
        verification_status="pending",
        created_at=_NOW,
    )


def _service(listing: _StubListingRepo, user: _StubUserRepo) -> AdminQueueService:
    return AdminQueueService(
        documents=listing,  # type: ignore[arg-type]
        user_documents=user,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_listing_source_maps_listing_fields_and_leaves_personal_ones_none() -> None:
    row = _listing_row()
    listing, user = _StubListingRepo([row]), _StubUserRepo([])
    result = await _service(listing, user).list_queue(
        source="listing", status="pending", page=1, page_size=20
    )

    item = result.data[0]
    assert item.source == "listing"
    assert item.listing_id == row.listing_id
    assert item.document_type == "c_of_o"
    assert item.user_id is None
    assert item.file_name is None
    # The other table must not even be queried.
    assert user.calls == []


@pytest.mark.asyncio
async def test_personal_source_maps_personal_fields_and_leaves_listing_ones_none() -> None:
    row = _personal_row()
    listing, user = _StubListingRepo([]), _StubUserRepo([row])
    result = await _service(listing, user).list_queue(
        source="personal", status="pending", page=1, page_size=20
    )

    item = result.data[0]
    assert item.source == "personal"
    assert item.user_id == row.user_id
    assert item.owner_name == "Ada Obi"
    assert item.category == "identity"
    assert item.file_name == "nin-slip.pdf"
    assert item.size_bytes == 2048
    assert item.listing_id is None
    assert item.document_type is None
    assert listing.calls == []


@pytest.mark.asyncio
async def test_missing_owner_name_is_passed_through_as_none() -> None:
    """A user with no user_pii row still has to appear in the queue."""
    listing, user = _StubListingRepo([]), _StubUserRepo([_personal_row(owner_name=None)])
    result = await _service(listing, user).list_queue(
        source="personal", status="pending", page=1, page_size=20
    )
    assert result.data[0].owner_name is None


@pytest.mark.asyncio
async def test_status_and_paging_reach_the_repository() -> None:
    listing, user = _StubListingRepo([]), _StubUserRepo([])
    await _service(listing, user).list_queue(
        source="listing", status="under_review", page=3, page_size=5
    )
    assert listing.calls == [{"status": "under_review", "page": 3, "page_size": 5}]


@pytest.mark.asyncio
async def test_total_pages_rounds_up_a_partial_last_page() -> None:
    listing, user = _StubListingRepo([_listing_row()], total=21), _StubUserRepo([])
    result = await _service(listing, user).list_queue(
        source="listing", status="pending", page=1, page_size=20
    )
    assert result.pagination.total == 21
    assert result.pagination.total_pages == 2


@pytest.mark.asyncio
async def test_empty_queue_reports_zero_pages() -> None:
    listing, user = _StubListingRepo([]), _StubUserRepo([])
    result = await _service(listing, user).list_queue(
        source="listing", status="pending", page=1, page_size=20
    )
    assert result.data == []
    assert result.pagination.total == 0
    assert result.pagination.total_pages == 0
