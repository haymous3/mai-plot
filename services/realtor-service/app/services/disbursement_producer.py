"""Commission disbursement producer (SCRUM-86 PR-B).

The actual money movement (escrow debit + payment_event + Paystack + receipt) is
owned by transaction-service. realtor-service triggers it by enqueuing the
`payments.disburse_commission` Celery task on the shared broker (the same
cross-service seam as notifications.dispatch). Best-effort: a broker outage is
logged, never raised — the next sweep re-enqueues.

  * CeleryDisbursementProducer — production. Fires the task by its stable name.
  * NullDisbursementProducer — dev/CI/tests. No-op, so no broker is needed.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_TASK = "payments.disburse_commission"


class DisbursementProducer(Protocol):
    async def request_disbursement(
        self,
        *,
        commission_id: UUID,
        transaction_id: UUID,
        realtor_id: UUID,
        seller_id: UUID,
        amount_kobo: int,
    ) -> None:  # pragma: no cover - protocol
        ...


class NullDisbursementProducer:
    async def request_disbursement(
        self,
        *,
        commission_id: UUID,
        transaction_id: UUID,
        realtor_id: UUID,
        seller_id: UUID,
        amount_kobo: int,
    ) -> None:
        return None


class CeleryDisbursementProducer:
    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def request_disbursement(
        self,
        *,
        commission_id: UUID,
        transaction_id: UUID,
        realtor_id: UUID,
        seller_id: UUID,
        amount_kobo: int,
    ) -> None:
        try:
            self._app.send_task(
                _TASK,
                kwargs={
                    "commission_id": str(commission_id),
                    "transaction_id": str(transaction_id),
                    "realtor_id": str(realtor_id),
                    "seller_id": str(seller_id),
                    "amount_kobo": amount_kobo,
                },
            )
        except Exception as exc:  # broker down etc. — never fail the sweep
            logger.warning(
                "commission.disburse.enqueue_failed",
                extra={"commission_id": str(commission_id), "error": str(exc)},
            )


def build_disbursement_producer(*, enabled: bool, broker_url: str) -> DisbursementProducer:
    if enabled:
        return CeleryDisbursementProducer(broker_url=broker_url)
    return NullDisbursementProducer()
