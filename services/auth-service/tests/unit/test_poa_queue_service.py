"""PoaQueueService — pagination passthrough + result shaping."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.user_repo import PoaQueueRow
from app.services.poa_queue import PoaQueueService


class _StubUserRepo:
    def __init__(self, rows: list[PoaQueueRow], total: int) -> None:
        self._rows = rows
        self._total = total
        self.called_with: dict[str, int] | None = None

    async def list_poa_queue(self, *, page: int, page_size: int) -> tuple[list[PoaQueueRow], int]:
        self.called_with = {"page": page, "page_size": page_size}
        return self._rows, self._total


@pytest.mark.asyncio
async def test_list_pending_returns_rows_and_total() -> None:
    row = PoaQueueRow(user_id=uuid4(), owner_name="Ada Lovelace", submitted_at=datetime.now(UTC))
    repo = _StubUserRepo([row], total=5)
    svc = PoaQueueService(users=repo)  # type: ignore[arg-type]

    page = await svc.list_pending(page=2, page_size=10)

    assert page.items == [row]
    assert page.total == 5
    assert page.page == 2 and page.page_size == 10
    assert repo.called_with == {"page": 2, "page_size": 10}
