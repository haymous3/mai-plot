"""Access to loan_repayment_milestones (SCRUM-77).

Milestones are reported by the bank's repayment.milestone webhook and tracked
here — Maiplot does not move the repayment money, it records what the bank
reports. One row per (loan_id, due_date); the webhook upserts so a corrected or
retried report updates the same slot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class MilestoneRow:
    id: UUID
    loan_id: UUID
    due_date: date
    amount_due_kobo: int
    amount_paid_kobo: int
    status: str
    paid_at: datetime | None
    bank_reference: str | None


@dataclass(frozen=True)
class RepaymentRollup:
    """Per-loan aggregate of its milestones (overdue is derived at read-time:
    a still-pending milestone whose due_date has passed)."""

    milestone_count: int
    paid_count: int
    overdue_count: int
    total_due_kobo: int
    total_paid_kobo: int


_COLUMNS = (
    "id, loan_id, due_date, amount_due_kobo, amount_paid_kobo, status, paid_at, bank_reference"
)


class RepaymentMilestoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_milestone(
        self,
        loan_id: UUID,
        *,
        due_date: date,
        amount_due_kobo: int,
        amount_paid_kobo: int,
        status: str,
        paid_at: datetime | None,
        bank_reference: str | None,
    ) -> bool:
        """Insert or update the milestone for (loan_id, due_date). Returns True if
        a new row was inserted, False if an existing one was updated (xmax = 0 is
        Postgres's tell for an insert vs a conflict-update)."""
        row = (
            (
                await self._session.execute(
                    text(
                        """
                    INSERT INTO loan_repayment_milestones
                        (loan_id, due_date, amount_due_kobo, amount_paid_kobo,
                         status, paid_at, bank_reference)
                    VALUES (:loan, :due, :due_kobo, :paid_kobo, :status, :paid_at, :ref)
                    ON CONFLICT (loan_id, due_date) WHERE deleted_at IS NULL
                    DO UPDATE SET
                        amount_due_kobo = EXCLUDED.amount_due_kobo,
                        amount_paid_kobo = EXCLUDED.amount_paid_kobo,
                        status = EXCLUDED.status,
                        paid_at = EXCLUDED.paid_at,
                        bank_reference = EXCLUDED.bank_reference,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                    """
                    ),
                    {
                        "loan": loan_id,
                        "due": due_date,
                        "due_kobo": amount_due_kobo,
                        "paid_kobo": amount_paid_kobo,
                        "status": status,
                        "paid_at": paid_at,
                        "ref": bank_reference,
                    },
                )
            )
            .mappings()
            .one()
        )
        return bool(row["inserted"])

    async def list_for_loan(self, loan_id: UUID) -> list[MilestoneRow]:
        rows = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM loan_repayment_milestones "
                    "WHERE loan_id = :loan AND deleted_at IS NULL "
                    "ORDER BY due_date ASC"
                ),
                {"loan": loan_id},
            )
        ).all()
        return [self._to_row(r) for r in rows]

    async def rollup_for_loans(self, loan_ids: list[UUID]) -> dict[UUID, RepaymentRollup]:
        """One aggregate row per loan over its milestones. Overdue = a pending
        milestone whose due_date is before today (derived, not stored)."""
        if not loan_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    text(
                        """
                    SELECT loan_id,
                           COUNT(*)                                          AS milestone_count,
                           COUNT(*) FILTER (WHERE status = 'paid')           AS paid_count,
                           COUNT(*) FILTER (
                               WHERE status = 'pending' AND due_date < CURRENT_DATE
                           )                                                 AS overdue_count,
                           COALESCE(SUM(amount_due_kobo), 0)                 AS total_due_kobo,
                           COALESCE(SUM(amount_paid_kobo), 0)                AS total_paid_kobo
                      FROM loan_repayment_milestones
                     WHERE loan_id = ANY(:ids) AND deleted_at IS NULL
                     GROUP BY loan_id
                    """
                    ),
                    {"ids": loan_ids},
                )
            )
            .mappings()
            .all()
        )
        return {
            r["loan_id"]: RepaymentRollup(
                milestone_count=int(r["milestone_count"]),
                paid_count=int(r["paid_count"]),
                overdue_count=int(r["overdue_count"]),
                total_due_kobo=int(r["total_due_kobo"]),
                total_paid_kobo=int(r["total_paid_kobo"]),
            )
            for r in rows
        }

    @staticmethod
    def _to_row(r: object) -> MilestoneRow:
        return MilestoneRow(
            id=r.id,  # type: ignore[attr-defined]
            loan_id=r.loan_id,  # type: ignore[attr-defined]
            due_date=r.due_date,  # type: ignore[attr-defined]
            amount_due_kobo=r.amount_due_kobo,  # type: ignore[attr-defined]
            amount_paid_kobo=r.amount_paid_kobo,  # type: ignore[attr-defined]
            status=r.status,  # type: ignore[attr-defined]
            paid_at=r.paid_at,  # type: ignore[attr-defined]
            bank_reference=r.bank_reference,  # type: ignore[attr-defined]
        )
