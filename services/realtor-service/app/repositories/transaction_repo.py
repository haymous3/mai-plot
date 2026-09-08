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
    # SCRUM-213: the listing's title, so an assignment alert can name the
    # property instead of telling a realtor to log in and find out where the job
    # is. LEFT JOIN, so a missing or soft-deleted listing leaves it None rather
    # than making the transaction unreadable.
    property_title: str | None


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transaction_id: UUID) -> TransactionInfo | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT t.id, t.listing_id, t.buyer_id, t.seller_id, t.stage, "
                    "pl.title AS property_title "
                    "FROM transactions t "
                    "LEFT JOIN property_listings pl ON pl.id = t.listing_id "
                    "WHERE t.id = :id"
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
            property_title=row.property_title,
        )
