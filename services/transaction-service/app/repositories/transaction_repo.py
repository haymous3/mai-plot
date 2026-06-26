"""Writes to transactions + transaction_events (the deal record).

A transaction is created when an offer is accepted, at the state machine's
initial stage 'offer_accepted'. transaction_events is the append-only log; the
first event records the acceptance. (Subsequent stage transitions are SCRUM-67.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TransactionStatus:
    stage: str
    buyer_id: UUID
    seller_id: UUID
    listing_id: UUID
    agreed_price_kobo: int
    # NULL until the platform fee is computed at deal close (SCRUM-119).
    platform_fee_kobo: int | None


@dataclass(frozen=True)
class ListingLock:
    """The latest transaction holding a listing's 72h lock — its stage and lock
    window decide whether an under_offer listing can be reopened (SCRUM-68)."""

    transaction_id: UUID
    stage: str
    lock_expires_at: datetime | None


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_status(self, transaction_id: UUID) -> TransactionStatus | None:
        """Current stage + parties + listing of a transaction (transition authz
        and the listing-status side effects on cancel/complete)."""
        row = (
            await self._session.execute(
                text(
                    "SELECT stage, buyer_id, seller_id, listing_id, "
                    "agreed_price_kobo, platform_fee_kobo "
                    "FROM transactions WHERE id = :id"
                ),
                {"id": transaction_id},
            )
        ).first()
        if row is None:
            return None
        return TransactionStatus(
            stage=row.stage,
            buyer_id=row.buyer_id,
            seller_id=row.seller_id,
            listing_id=row.listing_id,
            agreed_price_kobo=row.agreed_price_kobo,
            platform_fee_kobo=row.platform_fee_kobo,
        )

    async def get_user_email(self, user_id: UUID) -> str | None:
        """The user's email (shared users table) — Paystack needs it to initialise
        a charge (SCRUM-83). Cross-service read, like the accrual joins."""
        row = (
            await self._session.execute(
                text("SELECT email FROM users WHERE id = :id"),
                {"id": user_id},
            )
        ).first()
        return row.email if row is not None else None

    async def get_lock_for_listing(self, listing_id: UUID) -> ListingLock | None:
        """The most recent transaction for a listing (its stage + lock window),
        used to decide whether an under_offer listing's 72h lock has lapsed."""
        row = (
            await self._session.execute(
                text(
                    "SELECT id, stage, lock_expires_at FROM transactions "
                    "WHERE listing_id = :lid ORDER BY created_at DESC LIMIT 1"
                ),
                {"lid": listing_id},
            )
        ).first()
        if row is None:
            return None
        return ListingLock(
            transaction_id=row.id, stage=row.stage, lock_expires_at=row.lock_expires_at
        )

    async def update_stage(self, transaction_id: UUID, *, stage: str) -> None:
        await self._session.execute(
            text("UPDATE transactions SET stage = :s, updated_at = NOW() WHERE id = :id"),
            {"s": stage, "id": transaction_id},
        )

    async def set_platform_fee(self, transaction_id: UUID, *, fee_kobo: int) -> bool:
        """Persist the platform fee at deal close (SCRUM-119). Guarded on
        platform_fee_kobo IS NULL so the figure is written exactly once; returns
        False if a fee was already set (idempotent)."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE transactions SET platform_fee_kobo = :fee, updated_at = NOW() "
                    "WHERE id = :id AND platform_fee_kobo IS NULL "
                    "RETURNING id"
                ),
                {"fee": fee_kobo, "id": transaction_id},
            )
        ).first()
        return row is not None

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
