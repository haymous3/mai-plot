"""Cross-service read of loans (owned by loan-service) — SCRUM-131.

document-service reads a loan's buyer to authorise loan-document uploads/views,
the same shared-DB pattern used for listings/users. Becomes a REST call when the
databases are split.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LoanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_loan_buyer(self, loan_id: UUID) -> UUID | None:
        """The buyer who owns a loan, or None if there's no such live loan."""
        row = (
            await self._session.execute(
                text("SELECT buyer_id FROM loans WHERE id = :id AND deleted_at IS NULL"),
                {"id": loan_id},
            )
        ).first()
        return row.buyer_id if row is not None else None
