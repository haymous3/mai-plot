"""Read-only access to the transactions table (owned by transaction-service).

loan-service reads the deal over the shared DB to authorise the applicant and
size the 50% loan cap — the cross-service read pattern (transactions has no
deleted_at). When the databases split this becomes a REST call to
transaction-service.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TransactionInfo:
    buyer_id: UUID
    agreed_price_kobo: int
    stage: str


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transaction_id: UUID) -> TransactionInfo | None:
        row = (
            await self._session.execute(
                text("SELECT buyer_id, agreed_price_kobo, stage FROM transactions WHERE id = :id"),
                {"id": transaction_id},
            )
        ).first()
        if row is None:
            return None
        return TransactionInfo(
            buyer_id=row.buyer_id,
            agreed_price_kobo=row.agreed_price_kobo,
            stage=row.stage,
        )
