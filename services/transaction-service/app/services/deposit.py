"""Buyer escrow-deposit checkout (SCRUM-83) — §11.

Creates the payment_event BEFORE calling Paystack (review.md P8), validates the
amount server-side against the agreed price (P5), and returns the hosted checkout
URL. The Paystack reference IS the payment_event id, so the webhook can match the
charge back to the event. No money is credited here — that happens on the
webhook (charge.success -> escrow credit).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.paystack_charge import PaystackChargeClient
from app.repositories.payment_repo import PaymentEventRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser


class DepositError(RuntimeError):
    pass


class TransactionNotFound(DepositError):
    pass


class NotTransactionBuyer(DepositError):
    """Only the deal's buyer may fund its escrow."""


class AmountMismatch(DepositError):
    """The deposit must equal the buyer's required contribution — the agreed
    price, less any approved loan (the bank disburses that part separately)."""


class AlreadyDeposited(DepositError):
    """This deposit already completed — nothing more to pay."""


class BuyerEmailMissing(DepositError):
    """No email on file for the buyer; Paystack needs one to initialise."""


@dataclass(frozen=True)
class DepositResult:
    authorization_url: str
    reference: str
    payment_event_id: UUID


class DepositService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        payments: PaymentEventRepository,
        charge_client: PaystackChargeClient,
        callback_url: str,
    ) -> None:
        self._transactions = transactions
        self._payments = payments
        self._charge = charge_client
        self._callback_url = callback_url

    async def initiate(
        self,
        *,
        transaction_id: UUID,
        buyer: CurrentUser,
        idempotency_key: UUID,
        amount_kobo: int,
    ) -> DepositResult:
        status = await self._transactions.get_status(transaction_id)
        if status is None:
            raise TransactionNotFound()
        if status.buyer_id != buyer.user_id:
            raise NotTransactionBuyer()
        # Server-side amount validation (review.md P5): the buyer funds the agreed
        # price LESS any approved loan — the bank disburses that part straight to
        # escrow (SCRUM-128). No approved loan → the buyer pays the full price.
        approved_loan_kobo = await self._transactions.get_approved_loan_amount(transaction_id)
        required_kobo = status.agreed_price_kobo - (approved_loan_kobo or 0)
        if amount_kobo != required_kobo:
            raise AmountMismatch()

        email = await self._transactions.get_user_email(buyer.user_id)
        if not email:
            raise BuyerEmailMissing()

        # payment_event BEFORE the Paystack call (P8); idempotent on
        # (payer_id, idempotency_key). The reference we give Paystack is the
        # event id, so the webhook can match it back.
        pe = await self._payments.upsert(
            idempotency_key=idempotency_key,
            payer_id=buyer.user_id,
            payee_id=None,
            transaction_id=transaction_id,
            amount_kobo=amount_kobo,
            payment_type="buyer_deposit",
            provider="paystack",
            status="initiated",
        )
        if pe.status == "completed":
            raise AlreadyDeposited()

        init = await self._charge.initialize(
            reference=str(pe.id),
            amount_kobo=amount_kobo,
            email=email,
            callback_url=self._callback_url or None,
        )
        await self._payments.update_status(pe.id, "initiated", provider_reference=init.reference)
        return DepositResult(
            authorization_url=init.authorization_url,
            reference=init.reference,
            payment_event_id=pe.id,
        )
