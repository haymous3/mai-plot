"""Repayment-milestone + title-release webhook handling (SCRUM-77).

Two bank events, on the same public /webhooks/bank endpoint (HMAC verified by the
dispatcher):

  * repayment.milestone — the bank reports an installment's state. We upsert it
    into loan_repayment_milestones keyed on (loan_id, due_date); a corrected or
    retried report updates the same slot (idempotent). Maiplot does NOT move the
    repayment money — it records what the bank reports.
  * loan.fully_repaid — the loan is cleared, so the bank releases the held title
    (CLAUDE.md §8 rule 6). We mark the loan fully_repaid + set title_released_at
    (guarded → duplicate-safe) and notify the buyer. NO transaction state-machine
    change and NO money movement (SCRUM-77 design sign-off).

Overdue is NOT decided here — it's derived at read-time (a pending milestone past
its due_date). We still store whatever status the bank sends.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from app.repositories.loan_repo import LoanRepository
from app.repositories.repayment_repo import RepaymentMilestoneRepository
from app.services.loan_notifier import LoanNotifier

logger = logging.getLogger(__name__)

_MILESTONE_STATUSES = {"pending", "paid", "overdue"}


class RepaymentOutcome(StrEnum):
    recorded = "recorded"  # new milestone inserted
    updated = "updated"  # existing milestone updated
    released = "released"  # title released on full repayment
    duplicate = "duplicate"  # title already released — no-op
    unknown_loan = "unknown_loan"
    ignored = "ignored"


class LoanRepaymentWebhookService:
    def __init__(
        self,
        *,
        loans: LoanRepository,
        milestones: RepaymentMilestoneRepository,
        notifier: LoanNotifier,
    ) -> None:
        self._loans = loans
        self._milestones = milestones
        self._notifier = notifier

    async def handle_milestone(self, payload: dict[str, Any]) -> RepaymentOutcome:
        data = payload.get("data") or {}
        reference = data.get("reference") or data.get("bank_reference_id")
        due_date = _as_date(data.get("due_date"))
        if not reference or due_date is None:
            return RepaymentOutcome.ignored

        loan = await self._loans.get_by_bank_reference(str(reference))
        if loan is None:
            logger.warning("loan.repayment.unknown_reference")  # no PII / no reference
            return RepaymentOutcome.unknown_loan

        status = str(data.get("status") or "").strip().lower()
        if status not in _MILESTONE_STATUSES:
            status = "pending"

        inserted = await self._milestones.upsert_milestone(
            loan.id,
            due_date=due_date,
            amount_due_kobo=_as_int(data.get("amount_due_kobo")) or 0,
            amount_paid_kobo=_as_int(data.get("amount_paid_kobo")) or 0,
            status=status,
            paid_at=_as_datetime(data.get("paid_at")) if status == "paid" else None,
            bank_reference=_as_str(data.get("milestone_reference") or data.get("bank_reference")),
        )
        return RepaymentOutcome.recorded if inserted else RepaymentOutcome.updated

    async def handle_fully_repaid(self, payload: dict[str, Any]) -> RepaymentOutcome:
        data = payload.get("data") or {}
        reference = data.get("reference") or data.get("bank_reference_id")
        if not reference:
            return RepaymentOutcome.ignored

        loan = await self._loans.get_by_bank_reference(str(reference))
        if loan is None:
            logger.warning("loan.fully_repaid.unknown_reference")
            return RepaymentOutcome.unknown_loan

        released = await self._loans.mark_fully_repaid(loan.id)
        if not released:
            return RepaymentOutcome.duplicate  # title already released — bank retried

        await self._notifier.title_released(buyer_id=loan.buyer_id, loan_id=loan.id)
        logger.info("loan.title_released", extra={"loan_id": str(loan.id)})
        return RepaymentOutcome.released


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


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
