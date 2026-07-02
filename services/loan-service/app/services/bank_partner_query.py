"""Read-only bank-partner listing for the buyer calculator (SCRUM-94).

Backs GET /loans/bank-partners: the buyer's loan-financing page shows each active
partner's rate, tenure range, and loan band so they can pick a bank before
applying. Read-only, non-§11 — no application is created here. A Redis
`bank_partners:active` cache (CLAUDE.md §6, 1h TTL) is a follow-up; the read hits
the DB for now.
"""

from __future__ import annotations

from app.repositories.bank_partner_repo import BankPartnerRepository, BankPartnerSummary


class BankPartnerQueryService:
    def __init__(self, *, partners: BankPartnerRepository) -> None:
        self._partners = partners

    async def list_active(self) -> list[BankPartnerSummary]:
        return await self._partners.list_active()
