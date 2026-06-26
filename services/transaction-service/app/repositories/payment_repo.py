"""Access to payment_events (SCRUM-86) — the first writer of this table.

A payment_event is the idempotency anchor for every money movement: it is created
BEFORE the external transfer and its status walks initiated -> processing ->
completed | failed. App-layer idempotency is the UNIQUE (payer_id, idempotency_key)
upsert; the DB constraint is the last line of defence (data-model.md design #3).

Unlike escrow_ledger, payment_events is mutable (status + provider_reference get
updated as the transfer progresses) — NOT append-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PaymentEventRow:
    id: UUID
    status: str
    payment_type: str
    amount_kobo: int


@dataclass(frozen=True)
class PaymentEventDetail:
    id: UUID
    status: str
    payment_type: str
    amount_kobo: int
    transaction_id: UUID | None
    payer_id: UUID


class PaymentEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        idempotency_key: UUID,
        payer_id: UUID,
        payee_id: UUID | None,
        transaction_id: UUID,
        amount_kobo: int,
        payment_type: str,
        provider: str,
        status: str = "initiated",
    ) -> PaymentEventRow:
        """Create the payment_event, or return the existing one for this
        (payer_id, idempotency_key) — so a retried/duplicate disbursement reuses
        the same event and can never double-pay."""
        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO payment_events
                        (idempotency_key, payer_id, payee_id, transaction_id,
                         amount_kobo, payment_type, provider, status)
                    VALUES
                        (:ik, :payer, :payee, :tid, :amount, :ptype, :provider, :status)
                    ON CONFLICT (payer_id, idempotency_key) DO NOTHING
                    RETURNING id, status, payment_type, amount_kobo
                    """
                ),
                {
                    "ik": idempotency_key,
                    "payer": payer_id,
                    "payee": payee_id,
                    "tid": transaction_id,
                    "amount": amount_kobo,
                    "ptype": payment_type,
                    "provider": provider,
                    "status": status,
                },
            )
        ).first()
        if row is None:  # conflict — fetch the existing event
            row = (
                await self._session.execute(
                    text(
                        "SELECT id, status, payment_type, amount_kobo FROM payment_events "
                        "WHERE payer_id = :payer AND idempotency_key = :ik"
                    ),
                    {"payer": payer_id, "ik": idempotency_key},
                )
            ).one()
        return PaymentEventRow(
            id=row.id,
            status=row.status,
            payment_type=row.payment_type,
            amount_kobo=row.amount_kobo,
        )

    async def get(self, payment_event_id: UUID) -> PaymentEventDetail | None:
        """Look up a payment_event by id — used by the webhook to confirm a
        deposit (the Paystack reference is the payment_event id)."""
        row = (
            await self._session.execute(
                text(
                    "SELECT id, status, payment_type, amount_kobo, transaction_id, payer_id "
                    "FROM payment_events WHERE id = :id"
                ),
                {"id": payment_event_id},
            )
        ).first()
        if row is None:
            return None
        return PaymentEventDetail(
            id=row.id,
            status=row.status,
            payment_type=row.payment_type,
            amount_kobo=row.amount_kobo,
            transaction_id=row.transaction_id,
            payer_id=row.payer_id,
        )

    async def update_status(
        self, payment_event_id: UUID, status: str, *, provider_reference: str | None = None
    ) -> None:
        """Advance the event's status (and stamp the provider reference once the
        transfer is placed). provider_reference is only ever set, never cleared."""
        await self._session.execute(
            text(
                "UPDATE payment_events SET status = :status, "
                "provider_reference = COALESCE(:ref, provider_reference), "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"status": status, "ref": provider_reference, "id": payment_event_id},
        )
