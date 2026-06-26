"""Bank account-opened + disbursement webhook handling (SCRUM-129) — §11.

Two more bank-partner events on the shared /webhooks/bank endpoint:

  * account.opened — the bank opened the collateral account that holds the title
    (CLAUDE.md §8 rule 6). Flip bank_account_opened + notify the buyer. No money.
  * loan.disbursed — the bank released the approved loan into escrow. Flip
    approved → disbursed, ENQUEUE transaction-service's escrow credit (the money
    write lives there, SCRUM-128), then notify the buyer.

Idempotent via guarded UPDATEs (first webhook wins; bank retries are silent
no-ops → "duplicate", all HTTP 200).

The disbursement credit enqueue is deliberately NOT best-effort: `send_task`
raises on a broker outage and we let it propagate, so the whole request
transaction rolls back (the approved → disbursed flip is undone) and the bank
retries — an escrow credit must never be silently lost. The tx-service credit
task is itself idempotent (keyed per loan), so a retry can't double-credit.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from app.repositories.loan_repo import LoanRepository
from app.services.loan_notifier import LoanNotifier
from app.services.tx_tasks import TxTaskProducer

logger = logging.getLogger(__name__)


class DisbursementOutcome(StrEnum):
    account_opened = "account_opened"
    disbursed = "disbursed"
    duplicate = "duplicate"
    ignored = "ignored"
    unknown_loan = "unknown_loan"


class LoanDisbursementWebhookService:
    def __init__(
        self,
        *,
        loans: LoanRepository,
        notifier: LoanNotifier,
        tx_tasks: TxTaskProducer,
    ) -> None:
        self._loans = loans
        self._notifier = notifier
        self._tx_tasks = tx_tasks

    @staticmethod
    def _reference(payload: dict[str, Any]) -> str | None:
        data = payload.get("data") or {}
        ref = data.get("reference") or data.get("bank_reference_id")
        return str(ref) if ref else None

    async def handle_account_opened(self, payload: dict[str, Any]) -> DisbursementOutcome:
        reference = self._reference(payload)
        if not reference:
            return DisbursementOutcome.ignored

        loan = await self._loans.get_by_bank_reference(reference)
        if loan is None:
            logger.warning("loan.webhook.unknown_reference")  # no PII / no reference in log
            return DisbursementOutcome.unknown_loan

        if not await self._loans.mark_account_opened(loan.id):
            return DisbursementOutcome.duplicate  # already opened — bank retried

        await self._notifier.account_opened(buyer_id=loan.buyer_id, loan_id=loan.id)
        logger.info("loan.account_opened", extra={"loan_id": str(loan.id)})
        return DisbursementOutcome.account_opened

    async def handle_disbursed(self, payload: dict[str, Any]) -> DisbursementOutcome:
        reference = self._reference(payload)
        if not reference:
            return DisbursementOutcome.ignored

        loan = await self._loans.get_by_bank_reference(reference)
        if loan is None:
            logger.warning("loan.webhook.unknown_reference")
            return DisbursementOutcome.unknown_loan

        # An approved loan always carries its approved amount; refuse to disburse
        # an unknown amount rather than guess (we'd be crediting escrow blind).
        if loan.status != "approved" or loan.approved_amount_kobo is None:
            return DisbursementOutcome.duplicate

        if not await self._loans.mark_disbursed(loan.id):
            return DisbursementOutcome.duplicate  # raced with a concurrent webhook

        # Enqueue the escrow credit BEFORE returning — if the broker is down this
        # raises, the request transaction rolls back the disbursed flip, and the
        # bank retries (the credit task is idempotent, so no double-credit).
        self._tx_tasks.credit_loan_disbursement(
            loan_id=loan.id,
            transaction_id=loan.transaction_id,
            buyer_id=loan.buyer_id,
            amount_kobo=loan.approved_amount_kobo,
        )
        await self._notifier.disbursed(
            buyer_id=loan.buyer_id, loan_id=loan.id, amount_kobo=loan.approved_amount_kobo
        )
        logger.info("loan.disbursed", extra={"loan_id": str(loan.id)})
        return DisbursementOutcome.disbursed
