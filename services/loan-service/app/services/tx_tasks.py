"""Cross-service producer for transaction-service money/state tasks (SCRUM-129).

transaction-service owns the escrow ledger and the deal state machine, so
loan-service can only *trigger* those changes — it enqueues tx-service's Celery
tasks by their stable public names on the shared broker (CLAUDE.md §3: cross-
service async work goes via Celery, not a synchronous REST call), the same seam
the notifier uses:

  * payments.credit_loan_disbursement   (SCRUM-128) — escrow credit on disbursal
  * transactions.advance_loan_decision  (SCRUM-128) — loan_applied → approved/rejected

Unlike the notifier, these are NOT swallowed here: `send_task` raises on a broker
outage and the *caller* decides what to do with it. The disbursement webhook lets
it propagate (so the whole DB transaction rolls back and the bank retries — an
escrow credit must never be silently lost); the decision webhook treats the stage
advance as best-effort (the decision itself is already recorded + the buyer
notified).

  * CeleryTxTaskProducer — production. Fires the tasks by name.
  * NullTxTaskProducer    — dev/CI/tests. A no-op, so no broker is needed.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class TxTaskProducer(Protocol):
    def credit_loan_disbursement(
        self, *, loan_id: UUID, transaction_id: UUID, buyer_id: UUID, amount_kobo: int
    ) -> None:  # pragma: no cover - protocol
        ...

    def advance_loan_decision(
        self, *, transaction_id: UUID, decision: str
    ) -> None:  # pragma: no cover - protocol
        ...


class NullTxTaskProducer:
    """No-op producer — the default when tx tasks are disabled (no broker)."""

    def credit_loan_disbursement(
        self, *, loan_id: UUID, transaction_id: UUID, buyer_id: UUID, amount_kobo: int
    ) -> None:
        return None

    def advance_loan_decision(self, *, transaction_id: UUID, decision: str) -> None:
        return None


class CeleryTxTaskProducer:
    """Enqueues transaction-service's tasks on the shared broker by stable name."""

    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    def credit_loan_disbursement(
        self, *, loan_id: UUID, transaction_id: UUID, buyer_id: UUID, amount_kobo: int
    ) -> None:
        self._app.send_task(
            "payments.credit_loan_disbursement",
            kwargs={
                "loan_id": str(loan_id),
                "transaction_id": str(transaction_id),
                "buyer_id": str(buyer_id),
                "amount_kobo": amount_kobo,
            },
        )

    def advance_loan_decision(self, *, transaction_id: UUID, decision: str) -> None:
        self._app.send_task(
            "transactions.advance_loan_decision",
            kwargs={"transaction_id": str(transaction_id), "decision": decision},
        )


def build_tx_task_producer(*, enabled: bool, broker_url: str) -> TxTaskProducer:
    if enabled:
        return CeleryTxTaskProducer(broker_url=broker_url)
    return NullTxTaskProducer()
