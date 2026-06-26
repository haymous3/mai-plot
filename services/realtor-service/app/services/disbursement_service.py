"""Commission disbursement sweep (SCRUM-86 PR-B).

For each available commission, either:
  * reconcile — if transaction-service has already COMPLETED the payout
    (a completed realtor_commission payment_event exists), flip the commission
    'available' -> 'withdrawn' and link the payment_event; or
  * trigger — otherwise enqueue the `payments.disburse_commission` task so
    transaction-service does the escrow debit + transfer.

Idempotent + eventually-consistent: a commission is re-enqueued every tick until
its payout completes, then reconciled exactly once (mark_withdrawn is guarded on
status='available'). realtor-service never writes escrow_ledger/payment_events —
it only reads the completed event and writes its own commissions row.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.repositories.commission_repo import DisbursableCommission

logger = logging.getLogger(__name__)


class _Commissions(Protocol):
    async def list_disbursable(self, *, limit: int = 500) -> list[DisbursableCommission]: ...

    async def completed_disbursement(self, transaction_id: UUID) -> UUID | None: ...

    async def mark_withdrawn(self, transaction_id: UUID, *, payment_event_id: UUID) -> bool: ...


class _Producer(Protocol):
    async def request_disbursement(
        self,
        *,
        commission_id: UUID,
        transaction_id: UUID,
        realtor_id: UUID,
        seller_id: UUID,
        amount_kobo: int,
    ) -> None: ...


@dataclass(frozen=True)
class DisbursementResult:
    scanned: int
    withdrawn: int
    requested: int


class DisbursementService:
    def __init__(
        self, *, commissions: _Commissions, producer: _Producer, batch_limit: int = 500
    ) -> None:
        self._commissions = commissions
        self._producer = producer
        self._batch_limit = batch_limit

    async def run(self) -> DisbursementResult:
        disbursable = await self._commissions.list_disbursable(limit=self._batch_limit)
        withdrawn = 0
        requested = 0
        for c in disbursable:
            payment_event_id = await self._commissions.completed_disbursement(c.transaction_id)
            if payment_event_id is not None:
                if await self._commissions.mark_withdrawn(
                    c.transaction_id, payment_event_id=payment_event_id
                ):
                    withdrawn += 1
                continue
            # Not yet paid out — (re-)enqueue the transaction-service disbursement.
            await self._producer.request_disbursement(
                commission_id=c.commission_id,
                transaction_id=c.transaction_id,
                realtor_id=c.realtor_id,
                seller_id=c.seller_id,
                amount_kobo=c.amount_kobo,
            )
            requested += 1
        return DisbursementResult(
            scanned=len(disbursable), withdrawn=withdrawn, requested=requested
        )
