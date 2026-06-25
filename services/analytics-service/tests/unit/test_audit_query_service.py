"""Unit tests for AuditQueryService pagination (SCRUM-126)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.audit_repo import AuditLogRow, AuditQuery
from app.services.audit_query import AuditQueryService

pytestmark = pytest.mark.asyncio


def _row() -> AuditLogRow:
    return AuditLogRow(
        id=uuid4(),
        actor_id=None,
        actor_role="admin",
        action="listing.approved",
        entity_type="listing",
        entity_id=None,
        old_value=None,
        new_value=None,
        ip_address=None,
        user_agent=None,
        created_at=datetime.now(UTC),
    )


class _StubRepo:
    def __init__(self, *, total: int, rows: list[AuditLogRow]) -> None:
        self._total = total
        self._rows = rows
        self.list_args: tuple[int, int] | None = None

    async def count(self, query: AuditQuery) -> int:
        return self._total

    async def list(self, query: AuditQuery, *, limit: int, offset: int) -> list[AuditLogRow]:
        self.list_args = (limit, offset)
        return self._rows


def _service(repo: _StubRepo, *, default: int = 50, maximum: int = 200) -> AuditQueryService:
    return AuditQueryService(
        repo=repo,  # type: ignore[arg-type]
        default_page_size=default,
        max_page_size=maximum,
    )


async def test_uses_default_page_size_when_omitted() -> None:
    repo = _StubRepo(total=3, rows=[_row()])
    result = await _service(repo, default=50).list(query=AuditQuery(), page=1, page_size=None)
    assert result.pagination.page_size == 50
    assert repo.list_args == (50, 0)


async def test_clamps_page_size_to_max() -> None:
    repo = _StubRepo(total=0, rows=[])
    result = await _service(repo, maximum=200).list(query=AuditQuery(), page=1, page_size=1000)
    assert result.pagination.page_size == 200
    assert repo.list_args == (200, 0)


async def test_offset_and_total_pages() -> None:
    repo = _StubRepo(total=3, rows=[_row()])
    result = await _service(repo).list(query=AuditQuery(), page=2, page_size=2)
    assert repo.list_args == (2, 2)  # offset = (page-1)*size
    assert result.pagination.total_pages == 2  # ceil(3/2)


async def test_zero_total_is_zero_pages() -> None:
    repo = _StubRepo(total=0, rows=[])
    result = await _service(repo).list(query=AuditQuery(), page=1, page_size=20)
    assert result.pagination.total_pages == 0
    assert result.items == []
