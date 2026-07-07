"""Unit tests for ExpressInterestService (SCRUM-95)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.express_interest import ExpressInterestService

pytestmark = pytest.mark.asyncio


class _StubRepo:
    def __init__(self, created: bool = True) -> None:
        self._created = created
        self.calls: list[dict[str, object]] = []

    async def express(self, *, buyer_id: UUID, listing_id: UUID, message: str | None) -> bool:
        self.calls.append({"buyer_id": buyer_id, "listing_id": listing_id, "message": message})
        return self._created


async def test_trims_message_and_delegates() -> None:
    repo = _StubRepo(created=True)
    result = await ExpressInterestService(interests=repo).express(  # type: ignore[arg-type]
        buyer_id=uuid4(), listing_id=uuid4(), message="  hi there  "
    )
    assert result is True
    assert repo.calls[0]["message"] == "hi there"


async def test_blank_message_becomes_none() -> None:
    repo = _StubRepo()
    await ExpressInterestService(interests=repo).express(  # type: ignore[arg-type]
        buyer_id=uuid4(), listing_id=uuid4(), message="   "
    )
    assert repo.calls[0]["message"] is None


async def test_returns_false_for_repeat_interest() -> None:
    repo = _StubRepo(created=False)
    result = await ExpressInterestService(interests=repo).express(  # type: ignore[arg-type]
        buyer_id=uuid4(), listing_id=uuid4(), message=None
    )
    assert result is False
