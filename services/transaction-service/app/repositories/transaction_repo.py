"""Writes to transactions + transaction_events (the deal record).

A transaction is created when an offer is accepted, at the state machine's
initial stage 'offer_accepted'. transaction_events is the append-only log; the
first event records the acceptance. (Subsequent stage transitions are SCRUM-67.)
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_at_offer_accepted(
        self,
        *,
        listing_id: UUID,
        buyer_id: UUID,
        seller_id: UUID,
        agreed_price_kobo: int,
        lock_expires_at_sql: str,
    ) -> UUID:
        """Insert a transaction at stage 'offer_accepted' (the DB default) and
        return its id. lock_expires_at is set via a NOW()+interval expression."""
        txn_id = (
            await self._session.execute(
                text(
                    f"""
                    INSERT INTO transactions
                        (listing_id, buyer_id, seller_id, agreed_price_kobo, lock_expires_at)
                    VALUES (:lid, :bid, :sid, :price, {lock_expires_at_sql})
                    RETURNING id
                    """
                ),
                {"lid": listing_id, "bid": buyer_id, "sid": seller_id, "price": agreed_price_kobo},
            )
        ).scalar_one()
        assert isinstance(txn_id, UUID)
        return txn_id

    async def append_event(
        self,
        *,
        transaction_id: UUID,
        event_type: str,
        to_stage: str,
        triggered_by: UUID | None,
        from_stage: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Append an immutable transaction_events row."""
        await self._session.execute(
            text(
                """
                INSERT INTO transaction_events
                    (transaction_id, event_type, from_stage, to_stage, triggered_by, metadata)
                VALUES (:tid, :etype, :from_stage, :to_stage, :by, CAST(:meta AS jsonb))
                """
            ),
            {
                "tid": transaction_id,
                "etype": event_type,
                "from_stage": from_stage,
                "to_stage": to_stage,
                "by": triggered_by,
                "meta": json.dumps(metadata or {}),
            },
        )
