"""Unit tests for BankPartnerQueryService (SCRUM-94)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.repositories.bank_partner_repo import BankPartnerSummary
from app.services.bank_partner_query import BankPartnerQueryService

pytestmark = pytest.mark.asyncio


def _summary(name: str) -> BankPartnerSummary:
    return BankPartnerSummary(
        id=uuid4(),
        name=name,
        short_code=name[:4].upper(),
        loan_min_kobo=1_000_000,
        loan_max_kobo=500_000_000,
        interest_rate_bps=2200,
        min_tenure_months=6,
        max_tenure_months=36,
        requires_account_opening=True,
    )


class _StubPartners:
    def __init__(self, summaries: list[BankPartnerSummary]) -> None:
        self._summaries = summaries
        self.calls = 0

    async def list_active(self) -> list[BankPartnerSummary]:
        self.calls += 1
        return self._summaries


async def test_lists_active_partners() -> None:
    summaries = [_summary("Access Bank"), _summary("GTBank")]
    repo = _StubPartners(summaries)
    service = BankPartnerQueryService(partners=repo)  # type: ignore[arg-type]

    result = await service.list_active()

    assert result == summaries
    assert repo.calls == 1


async def test_empty_when_no_active_partners() -> None:
    repo = _StubPartners([])
    service = BankPartnerQueryService(partners=repo)  # type: ignore[arg-type]
    assert await service.list_active() == []
