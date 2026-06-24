"""Read-only access to transactions (owned by transaction-service, SCRUM-72).

realtor-service reads the transaction over the shared DB (the cross-service
pattern) to know the listing + who the parties are, so it can authorise an
inspection request and locate the property for assignment. When the databases
split this becomes a REST call to transaction-service.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TransactionInfo:
    id: UUID
    listing_id: UUID
    buyer_id: UUID
    seller_id: UUID
    stage: str


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transaction_id: UUID) -> TransactionInfo | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT id, listing_id, buyer_id, seller_id, stage "
                    "FROM transactions WHERE id = :id"
                ),
                {"id": transaction_id},
            )
        ).first()
        if row is None:
            return None
        return TransactionInfo(
            id=row.id,
            listing_id=row.listing_id,
            buyer_id=row.buyer_id,
            seller_id=row.seller_id,
            stage=row.stage,
        )
