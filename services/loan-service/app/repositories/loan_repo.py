"""Access to the loans table (owned by loan-service, SCRUM-75)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class LoanRow:
    id: UUID
    transaction_id: UUID
    buyer_id: UUID
    bank_partner_id: UUID
    requested_amount_kobo: int
    tenure_months: int | None
    status: str
    bank_reference_id: str | None
    created_at: datetime


_COLUMNS = (
    "id, transaction_id, buyer_id, bank_partner_id, requested_amount_kobo, "
    "tenure_months, status, bank_reference_id, created_at"
)


class LoanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        buyer_id: UUID,
        transaction_id: UUID,
        bank_partner_id: UUID,
        requested_amount_kobo: int,
        tenure_months: int,
        idempotency_key: UUID,
    ) -> tuple[UUID, bool]:
        """Insert a submitted loan. Idempotent on (buyer_id, idempotency_key):
        returns (loan_id, created) — created=False when the application was
        already recorded (re-POST with the same key)."""
        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO loans
                        (transaction_id, buyer_id, bank_partner_id,
                         requested_amount_kobo, tenure_months, idempotency_key)
                    VALUES (:tx, :buyer, :partner, :amount, :tenure, :ik)
                    ON CONFLICT (buyer_id, idempotency_key)
                        WHERE idempotency_key IS NOT NULL DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "tx": transaction_id,
                    "buyer": buyer_id,
                    "partner": bank_partner_id,
                    "amount": requested_amount_kobo,
                    "tenure": tenure_months,
                    "ik": idempotency_key,
                },
            )
        ).first()
        if row is not None:
            return row.id, True
        existing = (
            await self._session.execute(
                text("SELECT id FROM loans WHERE buyer_id = :buyer AND idempotency_key = :ik"),
                {"buyer": buyer_id, "ik": idempotency_key},
            )
        ).one()
        return existing.id, False

    async def set_bank_reference(
        self, loan_id: UUID, *, bank_reference_id: str, status: str
    ) -> None:
        await self._session.execute(
            text(
                "UPDATE loans SET bank_reference_id = :ref, status = :status, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"ref": bank_reference_id, "status": status, "id": loan_id},
        )

    async def get_by_idempotency(self, buyer_id: UUID, idempotency_key: UUID) -> LoanRow | None:
        """An already-recorded application for this (buyer, idempotency_key) — a
        re-POST returns it unchanged (no re-submission to the bank)."""
        row = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM loans "
                    "WHERE buyer_id = :buyer AND idempotency_key = :ik AND deleted_at IS NULL"
                ),
                {"buyer": buyer_id, "ik": idempotency_key},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def get_by_bank_reference(self, bank_reference_id: str) -> LoanRow | None:
        """The loan a bank decision webhook refers to, keyed by the reference the
        bank issued at submission (SCRUM-76)."""
        row = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM loans "
                    "WHERE bank_reference_id = :ref AND deleted_at IS NULL"
                ),
                {"ref": bank_reference_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def record_decision(
        self,
        loan_id: UUID,
        *,
        status: str,
        approved_amount_kobo: int | None,
        interest_rate_bps: int | None,
        tenure_months: int | None,
        monthly_instalment_kobo: int | None,
    ) -> bool:
        """Apply a bank decision (approved/rejected) to a still-pending loan.

        Guarded on the current status so a duplicate webhook (or one arriving
        after the decision was already recorded) is a silent no-op: the UPDATE
        only matches a loan still awaiting a decision. Returns True iff a row was
        updated (the first webhook wins)."""
        row = (
            await self._session.execute(
                text(
                    """
                    UPDATE loans
                       SET status = :status,
                           approved_amount_kobo = :approved,
                           interest_rate_bps = :rate,
                           tenure_months = COALESCE(:tenure, tenure_months),
                           monthly_instalment_kobo = :instalment,
                           bank_decision_at = NOW(),
                           updated_at = NOW()
                     WHERE id = :id
                       AND deleted_at IS NULL
                       AND status IN ('submitted', 'under_review', 'info_required')
                    RETURNING id
                    """
                ),
                {
                    "status": status,
                    "approved": approved_amount_kobo,
                    "rate": interest_rate_bps,
                    "tenure": tenure_months,
                    "instalment": monthly_instalment_kobo,
                    "id": loan_id,
                },
            )
        ).first()
        return row is not None

    async def get(self, loan_id: UUID) -> LoanRow | None:
        row = (
            await self._session.execute(
                text(f"SELECT {_COLUMNS} FROM loans WHERE id = :id AND deleted_at IS NULL"),
                {"id": loan_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def list_for_buyer(self, buyer_id: UUID) -> list[LoanRow]:
        rows = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM loans "
                    "WHERE buyer_id = :buyer AND deleted_at IS NULL "
                    "ORDER BY created_at DESC"
                ),
                {"buyer": buyer_id},
            )
        ).all()
        return [self._to_row(r) for r in rows]

    async def count_today(self, buyer_id: UUID) -> int:
        """How many applications this buyer has submitted since midnight UTC —
        the per-buyer daily cap (Kong only does 30/min)."""
        total = (
            await self._session.execute(
                text(
                    "SELECT COUNT(*) FROM loans WHERE buyer_id = :buyer "
                    "AND deleted_at IS NULL AND created_at >= date_trunc('day', NOW())"
                ),
                {"buyer": buyer_id},
            )
        ).scalar_one()
        return int(total)

    @staticmethod
    def _to_row(r: object) -> LoanRow:
        return LoanRow(
            id=r.id,  # type: ignore[attr-defined]
            transaction_id=r.transaction_id,  # type: ignore[attr-defined]
            buyer_id=r.buyer_id,  # type: ignore[attr-defined]
            bank_partner_id=r.bank_partner_id,  # type: ignore[attr-defined]
            requested_amount_kobo=r.requested_amount_kobo,  # type: ignore[attr-defined]
            tenure_months=r.tenure_months,  # type: ignore[attr-defined]
            status=r.status,  # type: ignore[attr-defined]
            bank_reference_id=r.bank_reference_id,  # type: ignore[attr-defined]
            created_at=r.created_at,  # type: ignore[attr-defined]
        )
