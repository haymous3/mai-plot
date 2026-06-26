"""Advance a transaction on a bank loan decision (SCRUM-128) — §11 (state machine).

When the bank decides a loan, the deal should reflect it: loan_applied →
loan_approved or loan_rejected. loan-service enqueues the
`transactions.advance_loan_decision` task that calls this; the state machine lives
in transaction-service, so the transition happens here (loan-service never mutates
the deal stage directly).

Uses the EXISTING transition table (state_machine.py) — no new transitions are
introduced. Guarded + idempotent: a decision is only applied from 'loan_applied'
(the legal source); a transaction already past it (a retried webhook, or a deal
that skipped the loan path) is a no-op, never an illegal jump.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.transaction_repo import TransactionRepository
from app.services.state_machine import can_transition

logger = logging.getLogger(__name__)

# Bank decision → the deal stage it advances loan_applied to.
_DECISION_STAGE: dict[str, str] = {
    "approved": "loan_approved",
    "rejected": "loan_rejected",
}


class AdvanceOutcome(StrEnum):
    advanced = "advanced"
    no_op = "no_op"  # not at loan_applied (already decided / different path)
    ignored = "ignored"  # unknown decision or unknown transaction


@dataclass(frozen=True)
class AdvanceResult:
    outcome: AdvanceOutcome
    stage: str | None  # the resulting stage when advanced, else the current one


class LoanDecisionStageService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        audit: AuditLogRepository,
        actor_id: UUID,
    ) -> None:
        self._transactions = transactions
        self._audit = audit
        self._actor_id = actor_id

    async def advance(self, *, transaction_id: UUID, decision: str) -> AdvanceResult:
        target = _DECISION_STAGE.get(decision)
        if target is None:
            return AdvanceResult(AdvanceOutcome.ignored, None)

        status = await self._transactions.get_status(transaction_id)
        if status is None:
            return AdvanceResult(AdvanceOutcome.ignored, None)

        # Idempotent guard: only a loan_applied deal advances on a decision. An
        # already-decided deal (retry) or one that never reached loan_applied is a
        # no-op — we never force an illegal transition.
        if not can_transition(status.stage, target):
            return AdvanceResult(AdvanceOutcome.no_op, status.stage)

        await self._transactions.update_stage(transaction_id, stage=target)
        await self._transactions.append_event(
            transaction_id=transaction_id,
            event_type="loan_decision",
            from_stage=status.stage,
            to_stage=target,
            triggered_by=self._actor_id,
            metadata={"decision": decision},
        )
        await self._audit.record(
            actor_id=self._actor_id,
            actor_role="system",
            action="transaction.stage_changed",
            entity_type="transaction",
            entity_id=transaction_id,
            old_value={"stage": status.stage},
            new_value={"stage": target, "decision": decision},
        )
        logger.info(
            "transaction.loan_decision_advanced",
            extra={"transaction_id": str(transaction_id), "to_stage": target},
        )
        return AdvanceResult(AdvanceOutcome.advanced, target)
