"""Access to bank_partners (owned by loan-service, SCRUM-75).

API credentials are NOT stored here (CLAUDE.md §10 — they're env/Secrets Manager);
this holds each partner's loan band, interest, and tenure bounds used to validate
an application. A Redis `bank_partners:active` cache (§6, 1h TTL) is a follow-up;
for now the read hits the DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class BankPartner:
    id: UUID
    short_code: str
    loan_min_kobo: int
    loan_max_kobo: int
    interest_rate_bps: int
    min_tenure_months: int
    max_tenure_months: int
    requires_account_opening: bool


_COLUMNS = (
    "id, short_code, loan_min_kobo, loan_max_kobo, interest_rate_bps, "
    "min_tenure_months, max_tenure_months, requires_account_opening"
)


class BankPartnerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, partner_id: UUID) -> BankPartner | None:
        row = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM bank_partners "
                    "WHERE id = :id AND is_active = TRUE AND deleted_at IS NULL"
                ),
                {"id": partner_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    @staticmethod
    def _to_row(r: object) -> BankPartner:
        return BankPartner(
            id=r.id,  # type: ignore[attr-defined]
            short_code=r.short_code,  # type: ignore[attr-defined]
            loan_min_kobo=r.loan_min_kobo,  # type: ignore[attr-defined]
            loan_max_kobo=r.loan_max_kobo,  # type: ignore[attr-defined]
            interest_rate_bps=r.interest_rate_bps,  # type: ignore[attr-defined]
            min_tenure_months=r.min_tenure_months,  # type: ignore[attr-defined]
            max_tenure_months=r.max_tenure_months,  # type: ignore[attr-defined]
            requires_account_opening=r.requires_account_opening,  # type: ignore[attr-defined]
        )
