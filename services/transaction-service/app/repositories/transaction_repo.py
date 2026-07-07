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
class LatestLoan:
    """The most recent loan application on a deal (SCRUM-94)."""

    loan_id: UUID
    status: str


@dataclass(frozen=True)
class ListingLock:
    """The latest transaction holding a listing's 72h lock — its stage and lock
    window decide whether an under_offer listing can be reopened (SCRUM-68)."""

    transaction_id: UUID
    stage: str
    lock_expires_at: datetime | None


@dataclass(frozen=True)
class SettleableDeal:
    """A completed deal whose seller-disbursement hold has elapsed (SCRUM-85)."""

    transaction_id: UUID
    buyer_id: UUID
    seller_id: UUID
    agreed_price_kobo: int
    platform_fee_kobo: int


@dataclass(frozen=True)
class CommissionGate:
    """What's known about a deal's realtor commission at settlement time —
    decides whether the seller disbursement can proceed yet (SCRUM-85)."""

    amount_kobo: int | None  # the accrued commission, or None if not recorded
    has_completed_inspection: bool  # a realtor was involved (commission expected)


@dataclass(frozen=True)
class DealRow:
    """A buyer's deal for the "Your Active Deals" list (SCRUM-95). Title +
    sale_type join from property_listings (owned by listing-service)."""

    id: UUID
    listing_id: UUID
    stage: str
    agreed_price_kobo: int
    created_at: datetime
    property_title: str | None
    sale_type: str | None


@dataclass(frozen=True)
class SellerDealRow:
    """A seller's transaction for the seller "Transactions" list (SCRUM-98).
    Same shape as DealRow plus the buyer id (surfaced masked)."""

    id: UUID
    listing_id: UUID
    buyer_id: UUID
    stage: str
    agreed_price_kobo: int
    created_at: datetime
    property_title: str | None
    sale_type: str | None


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_settleable(self, *, hold_hours: int, limit: int = 500) -> list[SettleableDeal]:
        """Completed deals whose platform fee is computed, whose hold has elapsed
        since they reached 'completed' (transaction_events), and which have no
        completed seller_disbursement yet."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT t.id, t.buyer_id, t.seller_id, t.agreed_price_kobo,
                           t.platform_fee_kobo
                    FROM transactions t
                    JOIN transaction_events e
                      ON e.transaction_id = t.id AND e.to_stage = 'completed'
                    WHERE t.stage = 'completed'
                      AND t.platform_fee_kobo IS NOT NULL
                      AND e.created_at <= NOW() - make_interval(hours => :hold)
                      AND NOT EXISTS (
                          SELECT 1 FROM payment_events pe
                          WHERE pe.transaction_id = t.id
                            AND pe.payment_type = 'seller_disbursement'
                            AND pe.status = 'completed')
                    ORDER BY e.created_at
                    LIMIT :limit
                    """
                ),
                {"hold": hold_hours, "limit": limit},
            )
        ).all()
        return [
            SettleableDeal(
                transaction_id=r.id,
                buyer_id=r.buyer_id,
                seller_id=r.seller_id,
                agreed_price_kobo=r.agreed_price_kobo,
                platform_fee_kobo=r.platform_fee_kobo,
            )
            for r in rows
        ]

    async def commission_gate(self, transaction_id: UUID) -> CommissionGate:
        """The deal's recorded realtor commission (cross-service read of
        realtor-service's commissions) + whether a realtor was involved at all."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                      (SELECT amount_kobo FROM commissions WHERE transaction_id = :id)
                          AS commission_kobo,
                      EXISTS (SELECT 1 FROM inspections
                              WHERE transaction_id = :id AND status = 'completed')
                          AS has_inspection
                    """
                ),
                {"id": transaction_id},
            )
        ).one()
        return CommissionGate(
            amount_kobo=row.commission_kobo,
            has_completed_inspection=bool(row.has_inspection),
        )

    async def get_approved_loan_amount(self, transaction_id: UUID) -> int | None:
        """The approved loan amount for a deal, if a loan has been approved
        (cross-service read of loan-service's loans, like the commission joins).
        Used to reduce the buyer's required escrow deposit to price − loan
        (SCRUM-128). None when there is no approved loan → buyer pays full price
        (the cash path). 'rejected' loans null their approved amount, so filtering
        on approved_amount_kobo IS NOT NULL already excludes them."""
        row = (
            await self._session.execute(
                text(
                    "SELECT approved_amount_kobo FROM loans "
                    "WHERE transaction_id = :id AND deleted_at IS NULL "
                    "AND approved_amount_kobo IS NOT NULL "
                    "ORDER BY bank_decision_at DESC NULLS LAST LIMIT 1"
                ),
                {"id": transaction_id},
            )
        ).first()
        return row.approved_amount_kobo if row is not None else None

    async def get_latest_loan(self, transaction_id: UUID) -> LatestLoan | None:
        """The most recent loan application for a deal, if any (cross-service read
        of loan-service's loans). Lets the financing page route a buyer who has
        already applied to their loan's status instead of re-applying (SCRUM-94)."""
        row = (
            await self._session.execute(
                text(
                    "SELECT id, status FROM loans "
                    "WHERE transaction_id = :id AND deleted_at IS NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"id": transaction_id},
            )
        ).first()
        if row is None:
            return None
        return LatestLoan(loan_id=row.id, status=row.status)

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

    async def list_for_buyer(self, buyer_id: UUID) -> list[DealRow]:
        """A buyer's deals (transactions), newest first, with the property title
        joined from property_listings (shared-DB cross-service read)."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT t.id, t.listing_id, t.stage, t.agreed_price_kobo, t.created_at,
                           pl.title AS property_title, pl.sale_type
                    FROM transactions t
                    LEFT JOIN property_listings pl ON pl.id = t.listing_id
                    WHERE t.buyer_id = :buyer_id
                    ORDER BY t.created_at DESC
                    """
                ),
                {"buyer_id": buyer_id},
            )
        ).all()
        return [
            DealRow(
                id=r.id,
                listing_id=r.listing_id,
                stage=r.stage,
                agreed_price_kobo=r.agreed_price_kobo,
                created_at=r.created_at,
                property_title=r.property_title,
                sale_type=r.sale_type,
            )
            for r in rows
        ]

    async def list_for_seller(self, seller_id: UUID) -> list[SellerDealRow]:
        """A seller's transactions, newest first, with the property title joined
        from property_listings (shared-DB cross-service read)."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT t.id, t.listing_id, t.buyer_id, t.stage, t.agreed_price_kobo,
                           t.created_at, pl.title AS property_title, pl.sale_type
                    FROM transactions t
                    LEFT JOIN property_listings pl ON pl.id = t.listing_id
                    WHERE t.seller_id = :seller_id
                    ORDER BY t.created_at DESC
                    """
                ),
                {"seller_id": seller_id},
            )
        ).all()
        return [
            SellerDealRow(
                id=r.id,
                listing_id=r.listing_id,
                buyer_id=r.buyer_id,
                stage=r.stage,
                agreed_price_kobo=r.agreed_price_kobo,
                created_at=r.created_at,
                property_title=r.property_title,
                sale_type=r.sale_type,
            )
            for r in rows
        ]

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
