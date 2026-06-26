"""Loan decision notification (SCRUM-76).

When a bank partner's `loan.decision_ready` webhook lands, the buyer is told the
outcome (in-app + SMS + email — a loan decision is a critical-path event per
CLAUDE.md §4). Delivery is owned by notification-service; this is the producer
side — it enqueues the `notifications.dispatch` Celery task on the shared broker
(CLAUDE.md §3: cross-service async work goes via Celery, not a synchronous REST
call), the same seam the other services use.

Sending is BEST-EFFORT: a broker outage is logged, never raised, so it can never
roll back the committed loan decision. Two impls:

  * CeleryLoanNotifier — production. Fires the task by its stable public name.
  * NullLoanNotifier — dev/CI/tests. A no-op, so no broker is needed.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


def _decision_message(*, decision: str, approved_amount_kobo: int | None) -> tuple[str, str, str]:
    """Return (type, title, body) for an approve/reject loan decision."""
    if decision == "approved":
        body = "Good news — your loan application has been approved by the bank."
        if approved_amount_kobo is not None:
            naira = approved_amount_kobo // 100
            body = (
                f"Good news — your loan application has been approved for ₦{naira:,} by the bank."
            )
        return "loan_approved", "Loan approved", body
    return (
        "loan_rejected",
        "Loan application declined",
        "Your loan application was not approved by the bank. You may explore other options.",
    )


_TITLE_RELEASED_BODY = (
    "Your loan is fully repaid — the bank has released your title documents. "
    "Congratulations, the property is fully yours."
)


class LoanNotifier(Protocol):
    async def loan_decision(
        self,
        *,
        buyer_id: UUID,
        loan_id: UUID,
        decision: str,
        approved_amount_kobo: int | None,
    ) -> None:  # pragma: no cover - protocol
        ...

    async def title_released(
        self, *, buyer_id: UUID, loan_id: UUID
    ) -> None:  # pragma: no cover - protocol
        ...


class NullLoanNotifier:
    """No-op notifier — the default when notifications are disabled (no broker)."""

    async def loan_decision(
        self,
        *,
        buyer_id: UUID,
        loan_id: UUID,
        decision: str,
        approved_amount_kobo: int | None,
    ) -> None:
        return None

    async def title_released(self, *, buyer_id: UUID, loan_id: UUID) -> None:
        return None


class CeleryLoanNotifier:
    """Enqueues `notifications.dispatch` on the shared broker, best-effort."""

    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    def _dispatch(
        self, *, buyer_id: UUID, loan_id: UUID, type_: str, title: str, body: str
    ) -> None:
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(buyer_id),
                    "type": type_,
                    "title": title,
                    "body": body,
                    "channels": ["in_app", "sms", "email"],
                    "reference_type": "loan",
                    "reference_id": str(loan_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the committed event
            logger.warning(
                "loan.notify_failed",
                extra={"loan_id": str(loan_id), "type": type_, "error": str(exc)},
            )

    async def loan_decision(
        self,
        *,
        buyer_id: UUID,
        loan_id: UUID,
        decision: str,
        approved_amount_kobo: int | None,
    ) -> None:
        type_, title, body = _decision_message(
            decision=decision, approved_amount_kobo=approved_amount_kobo
        )
        self._dispatch(buyer_id=buyer_id, loan_id=loan_id, type_=type_, title=title, body=body)

    async def title_released(self, *, buyer_id: UUID, loan_id: UUID) -> None:
        self._dispatch(
            buyer_id=buyer_id,
            loan_id=loan_id,
            type_="title_released",
            title="Title documents released",
            body=_TITLE_RELEASED_BODY,
        )


def build_loan_notifier(*, enabled: bool, broker_url: str) -> LoanNotifier:
    if enabled:
        return CeleryLoanNotifier(broker_url=broker_url)
    return NullLoanNotifier()
