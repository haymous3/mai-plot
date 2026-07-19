"""Failed-payout escrow reversal sweep (SCRUM-147) — §11, moves money in escrow.

Closes the deferral the payout chain (SCRUM-145) created: a payout records an
escrow DEBIT, then places an async Paystack transfer. If that transfer later
FAILS (the transfer.failed webhook, PR3), the payment_event is marked `failed`
but the debit stays on the ledger — so the escrow balance understates what the
deal still holds, and the payout can't be cleanly retried.

This beat sweep finds those failed payouts with a standing, unreversed debit and
records a compensating CREDIT (via EscrowLedgerService.reverse_debit) that puts
the money back. Idempotent + re-entrant: the repo query excludes any payout that
already has a reversal credit, so re-running never double-credits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.repositories.escrow_repo import EscrowLedgerRepository
from app.services.escrow_ledger import EscrowLedgerService

logger = logging.getLogger(__name__)

# Outbound payout payment_types whose failed transfers leave a standing debit.
_PAYOUT_TYPES = ("realtor_commission", "seller_disbursement")
_REASON = "paystack transfer failed"


@dataclass(frozen=True)
class ReconcileResult:
    scanned: int
    reversed: int


class PayoutReconciliationService:
    def __init__(
        self,
        *,
        ledger: EscrowLedgerRepository,
        escrow: EscrowLedgerService,
        actor_id: UUID,
        batch_limit: int = 500,
    ) -> None:
        self._ledger = ledger
        self._escrow = escrow
        self._actor_id = actor_id
        self._batch_limit = batch_limit

    async def run(self) -> ReconcileResult:
        failed = await self._ledger.list_failed_payouts_needing_reversal(
            payout_types=_PAYOUT_TYPES, limit=self._batch_limit
        )
        reversed_count = 0
        for payout in failed:
            await self._escrow.reverse_debit(
                transaction_id=payout.transaction_id,
                amount_kobo=payout.debit_kobo,
                payment_event_id=payout.payment_event_id,
                reason=_REASON,
                recorded_by=self._actor_id,
            )
            reversed_count += 1
        if reversed_count:
            logger.info("payout.reconcile.reversed", extra={"count": reversed_count})
        return ReconcileResult(scanned=len(failed), reversed=reversed_count)
