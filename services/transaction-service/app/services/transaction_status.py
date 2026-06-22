"""Transaction status transitions (SCRUM-67).

Applies a stage change to a transaction, enforced by the state machine. Every
transition is recorded twice: an append-only transaction_events row (the deal's
own log) and an audit_log entry (CLAUDE.md — audit on every state change). Only
a party to the transaction (buyer/seller) or an admin may drive a transition.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser
from app.services import state_machine

logger = logging.getLogger(__name__)


class TransactionStatusError(RuntimeError):
    pass


class TransactionNotFound(TransactionStatusError):
    """No transaction with that id."""


class NotTransactionParty(TransactionStatusError):
    """Caller is neither a party to the transaction nor an admin."""


class InvalidStateTransition(TransactionStatusError):
    """The requested stage is not reachable from the current one."""


class TransactionStatusService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        audit: AuditLogRepository,
        listings: ListingRepository,
    ) -> None:
        self._transactions = transactions
        self._audit = audit
        self._listings = listings

    async def change_status(
        self,
        *,
        transaction_id: UUID,
        caller: CurrentUser,
        target_stage: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        status = await self._transactions.get_status(transaction_id)
        if status is None:
            raise TransactionNotFound()
        if caller.role != "admin" and caller.user_id not in (status.buyer_id, status.seller_id):
            raise NotTransactionParty()
        if not state_machine.can_transition(status.stage, target_stage):
            raise InvalidStateTransition()

        await self._transactions.update_stage(transaction_id, stage=target_stage)
        await self._transactions.append_event(
            transaction_id=transaction_id,
            event_type=target_stage,
            from_stage=status.stage,
            to_stage=target_stage,
            triggered_by=caller.user_id,
        )
        await self._audit.record(
            actor_id=caller.user_id,
            actor_role=caller.role,
            action=f"transaction.{target_stage}",
            entity_type="transaction",
            entity_id=transaction_id,
            old_value={"stage": status.stage},
            new_value={"stage": target_stage},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # End-of-deal side effects on the listing's 72h lock: a cancelled deal
        # reopens the listing; a completed deal closes it as sold (SCRUM-68).
        if target_stage == "cancelled":
            await self._listings.release_lock(status.listing_id)
        elif target_stage == "completed":
            await self._listings.mark_sold(status.listing_id)
        logger.info(
            "transaction.stage_changed",
            extra={
                "transaction_id": str(transaction_id),
                "from": status.stage,
                "to": target_stage,
            },
        )
        return target_stage
