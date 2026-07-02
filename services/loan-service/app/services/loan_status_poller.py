"""Loan status polling fallback (SCRUM-130).

A safety net for a delayed or dropped `loan.decision_ready` webhook: poll the bank
for loans still pending past a stale threshold and apply any decision through the
SAME path the webhook uses (LoanDecisionWebhookService.apply_for_loan), so there's
exactly one decision-application code path.

Idempotent by construction — apply_for_loan's guarded record_decision only matches
a still-pending loan, so if the webhook later arrives (or two polls race) it's a
silent no-op. Resilient: a bank error on one loan is logged and the sweep moves on.

Only loans that have a bank reference (already submitted) and an active partner are
polled. With the fake adapter `get_status` always reports under_review, so a
dev/CI poll is a harmless no-op.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.adapters.bank import BankAdapterError, BankAdapterRegistry
from app.repositories.loan_repo import LoanRepository
from app.services.loan_decision import LoanDecisionWebhookService

logger = logging.getLogger(__name__)

# Bank statuses that represent a final decision worth applying. under_review /
# info_required / submitted mean "keep waiting" — skip.
_DECIDED = {"approved", "rejected"}


@dataclass(frozen=True)
class PollResult:
    scanned: int
    decided: int
    errors: int


class LoanStatusPoller:
    def __init__(
        self,
        *,
        loans: LoanRepository,
        registry: BankAdapterRegistry,
        decisions: LoanDecisionWebhookService,
        stale_minutes: int,
        batch_limit: int,
    ) -> None:
        self._loans = loans
        self._registry = registry
        self._decisions = decisions
        self._stale_minutes = stale_minutes
        self._batch_limit = batch_limit

    async def run(self) -> PollResult:
        pollable = await self._loans.list_pollable(
            older_than_minutes=self._stale_minutes, limit=self._batch_limit
        )
        decided = 0
        errors = 0
        for item in pollable:
            try:
                adapter = self._registry.for_partner(short_code=item.short_code)
                result = await adapter.get_status(item.bank_reference_id)
            except BankAdapterError:
                # Bank unreachable for this loan — log and keep going; the next
                # sweep (or the webhook) will catch it.
                errors += 1
                logger.warning("loan.poll.get_status_failed", extra={"loan_id": str(item.loan.id)})
                continue

            if result.status not in _DECIDED:
                continue  # still pending — nothing to apply yet

            outcome = await self._decisions.apply_for_loan(
                item.loan,
                decision=result.status,
                approved_amount_kobo=result.approved_amount_kobo,
                interest_rate_bps=result.interest_rate_bps,
                tenure_months=result.tenure_months,
                monthly_instalment_kobo=result.monthly_instalment_kobo,
            )
            if outcome.value == "decided":
                decided += 1
                logger.info(
                    "loan.poll.decision_applied",
                    extra={"loan_id": str(item.loan.id), "decision": result.status},
                )

        return PollResult(scanned=len(pollable), decided=decided, errors=errors)
