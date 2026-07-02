"""Bank decision webhook handling (SCRUM-76) — §11.

A bank partner POSTs `loan.decision_ready` when an application is approved or
rejected. The endpoint is public (the bank's servers call it); authenticity is
the HMAC-SHA256 signature over the RAW body, keyed by the per-bank webhook
secret (review.md §5). On a verified decision we update loans.status (+ the
approved terms) and notify the buyer. We do NOT move money or touch the
transaction state machine here — escrow disbursement on approval is a later
ticket (SCRUM-77).

Idempotent: the status update is guarded to a still-pending loan, so a duplicate
webhook (banks retry) is silently a no-op (the AC: "duplicate webhooks silently
deduplicated").
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from enum import StrEnum
from typing import Any

from app.repositories.loan_repo import LoanRepository, LoanRow
from app.services.loan_notifier import LoanNotifier
from app.services.tx_tasks import TxTaskProducer

logger = logging.getLogger(__name__)

_DECISION_EVENT = "loan.decision_ready"
_VALID_DECISIONS = {"approved", "rejected"}


class DecisionOutcome(StrEnum):
    decided = "decided"
    duplicate = "duplicate"
    ignored = "ignored"
    unknown_loan = "unknown_loan"


class LoanDecisionWebhookService:
    def __init__(
        self,
        *,
        loans: LoanRepository,
        notifier: LoanNotifier,
        tx_tasks: TxTaskProducer,
        secret: str,
    ) -> None:
        self._loans = loans
        self._notifier = notifier
        self._tx_tasks = tx_tasks
        self._secret = secret

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """HMAC-SHA256 of the raw body, constant-time compared to the header."""
        if not signature:
            return False
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle(self, payload: dict[str, Any]) -> DecisionOutcome:
        if payload.get("event") != _DECISION_EVENT:
            return DecisionOutcome.ignored

        data = payload.get("data") or {}
        reference = data.get("reference") or data.get("bank_reference_id")
        decision = str(data.get("decision") or "").strip().lower()
        if not reference or decision not in _VALID_DECISIONS:
            return DecisionOutcome.ignored

        loan = await self._loans.get_by_bank_reference(str(reference))
        if loan is None:
            logger.warning("loan.webhook.unknown_reference")  # no PII / no reference in log
            return DecisionOutcome.unknown_loan

        return await self.apply_for_loan(
            loan,
            decision=decision,
            approved_amount_kobo=_as_int(data.get("approved_amount_kobo")),
            interest_rate_bps=_as_int(data.get("interest_rate_bps")),
            tenure_months=_as_int(data.get("tenure_months")),
            monthly_instalment_kobo=_as_int(data.get("monthly_instalment_kobo")),
        )

    async def apply_for_loan(
        self,
        loan: LoanRow,
        *,
        decision: str,
        approved_amount_kobo: int | None,
        interest_rate_bps: int | None,
        tenure_months: int | None,
        monthly_instalment_kobo: int | None,
    ) -> DecisionOutcome:
        """Apply a verified bank decision (approved/rejected) to a fetched loan:
        record it (guarded), advance the deal, and notify the buyer. Shared by the
        webhook (SCRUM-76) and the polling fallback (SCRUM-130) so both go through
        one path. `decision` must already be approved/rejected; the terms are
        nulled here on a rejection. Idempotent: the guarded record_decision only
        matches a still-pending loan, so an already-decided loan (or a concurrent
        webhook/poll) is a silent `duplicate`."""
        if loan.status not in ("submitted", "under_review", "info_required"):
            return DecisionOutcome.duplicate  # already decided

        approved = decision == "approved"
        updated = await self._loans.record_decision(
            loan.id,
            status="approved" if approved else "rejected",
            approved_amount_kobo=approved_amount_kobo if approved else None,
            interest_rate_bps=interest_rate_bps if approved else None,
            tenure_months=tenure_months if approved else None,
            monthly_instalment_kobo=monthly_instalment_kobo if approved else None,
        )
        if not updated:  # raced with a concurrent identical webhook/poll
            return DecisionOutcome.duplicate

        # Advance the deal loan_applied → loan_approved/loan_rejected (SCRUM-128
        # task in tx-service). BEST-EFFORT: a broker outage is logged, never
        # raised — the decision is already recorded and the buyer is notified, and
        # the advance is idempotent (no-op off loan_applied), so a future
        # reconciliation can re-fire it. We do NOT roll back a recorded decision
        # just because the deal stage couldn't be nudged.
        try:
            self._tx_tasks.advance_loan_decision(
                transaction_id=loan.transaction_id,
                decision="approved" if approved else "rejected",
            )
        except Exception as exc:  # broker down etc.
            logger.warning(
                "loan.advance_enqueue_failed",
                extra={"loan_id": str(loan.id), "error": str(exc)},
            )

        await self._notifier.loan_decision(
            buyer_id=loan.buyer_id,
            loan_id=loan.id,
            decision="approved" if approved else "rejected",
            approved_amount_kobo=approved_amount_kobo if approved else None,
        )
        logger.info("loan.decision.recorded", extra={"loan_id": str(loan.id), "decision": decision})
        return DecisionOutcome.decided


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (str, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None
