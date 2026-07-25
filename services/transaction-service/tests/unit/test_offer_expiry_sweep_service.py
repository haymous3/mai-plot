"""Unit tests for OfferExpirySweepService (SCRUM-118)."""

from __future__ import annotations

import pytest

from app.services.offer_expiry_sweep import OfferExpirySweepService

pytestmark = pytest.mark.asyncio


class _StubOfferRepo:
    def __init__(self, expired: int) -> None:
        self._expired = expired
        self.calls: list[int] = []

    async def expire_lapsed(self, *, limit: int = 500) -> int:
        self.calls.append(limit)
        return self._expired


async def test_expires_and_reports_the_count() -> None:
    repo = _StubOfferRepo(4)
    svc = OfferExpirySweepService(offers=repo)  # type: ignore[arg-type]

    result = await svc.run()

    assert result.expired == 4
    assert repo.calls == [500]


async def test_nothing_lapsed_is_a_noop() -> None:
    repo = _StubOfferRepo(0)
    svc = OfferExpirySweepService(offers=repo)  # type: ignore[arg-type]

    result = await svc.run()

    assert result == type(result)(expired=0)
