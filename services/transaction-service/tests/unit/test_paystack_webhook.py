"""Unit tests for PaystackWebhookService (SCRUM-83 deposit; SCRUM-145 payout)."""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.repositories.payment_repo import PaymentEventDetail
from app.services.paystack_webhook import PaystackWebhookService, WebhookOutcome

pytestmark = pytest.mark.asyncio

_SECRET = "test-webhook-secret"
_AMOUNT = 5_000_000_000


class _StubPayments:
    def __init__(self, detail: PaymentEventDetail | None) -> None:
        self._detail = detail
        self.updates: list[tuple[str, str | None]] = []

    async def get(self, payment_event_id: UUID) -> PaymentEventDetail | None:
        return self._detail

    async def update_status(
        self, payment_event_id: UUID, status: str, *, provider_reference: str | None = None
    ) -> None:
        self.updates.append((status, provider_reference))


class _StubEscrow:
    def __init__(self) -> None:
        self.credits: list[int] = []

    async def record_credit(
        self,
        *,
        transaction_id: UUID,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        recorded_by: UUID | None = None,
    ) -> UUID:
        self.credits.append(amount_kobo)
        return uuid4()


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


class _StubReceipts:
    def __init__(self) -> None:
        self.written: list[UUID] = []

    async def write_receipt(self, payment_event_id: UUID, data: dict[str, object]) -> str:
        self.written.append(payment_event_id)
        return f"receipts/{payment_event_id}.json"

    async def write_pdf_receipt(
        self, payment_event_id: UUID, *, title: str, fields: dict[str, object]
    ) -> str:
        self.written.append(payment_event_id)
        return f"receipts/{payment_event_id}.pdf"


def _detail(
    *, pe_id: UUID, status: str = "initiated", payment_type: str = "buyer_deposit"
) -> PaymentEventDetail:
    return PaymentEventDetail(
        id=pe_id,
        status=status,
        payment_type=payment_type,
        amount_kobo=_AMOUNT,
        transaction_id=uuid4(),
        payer_id=uuid4(),
    )


class _StubTransactions:
    """Just enough of TransactionRepository for the seller lookup (SCRUM-195)."""

    def __init__(self, seller_id: UUID | None = None, *, raises: bool = False) -> None:
        self.seller_id = seller_id or uuid4()
        self._raises = raises

    async def get_status(self, transaction_id: UUID) -> object | None:
        if self._raises:
            raise RuntimeError("db down")
        if self.seller_id is None:
            return None
        return SimpleNamespace(
            stage="payment_held",
            buyer_id=uuid4(),
            seller_id=self.seller_id,
            listing_id=uuid4(),
            agreed_price_kobo=_AMOUNT,
            platform_fee_kobo=None,
        )


class _StubSellers:
    def __init__(self, *, raises: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self._raises = raises

    async def offer_received(self, **kwargs: object) -> None:
        return None

    async def deposit_confirmed(
        self, *, seller_id: UUID, transaction_id: UUID, amount_kobo: int
    ) -> None:
        if self._raises:
            raise RuntimeError("broker down")
        self.calls.append(
            {
                "seller_id": seller_id,
                "transaction_id": transaction_id,
                "amount_kobo": amount_kobo,
            }
        )


def _service(
    payments: _StubPayments,
    escrow: _StubEscrow,
    receipts: _StubReceipts | None = None,
    audit: _StubAudit | None = None,
    transactions: _StubTransactions | None = None,
    sellers: _StubSellers | None = None,
) -> PaystackWebhookService:
    return PaystackWebhookService(
        payments=payments,  # type: ignore[arg-type]
        escrow=escrow,  # type: ignore[arg-type]
        receipts=receipts or _StubReceipts(),
        audit=audit or _StubAudit(),  # type: ignore[arg-type]
        secret=_SECRET,
        transactions=transactions,  # type: ignore[arg-type]
        sellers=sellers,
    )


def _charge_success(pe_id: UUID, amount: int = _AMOUNT) -> dict[str, object]:
    return {"event": "charge.success", "data": {"reference": str(pe_id), "amount": amount}}


def _transfer_event(
    event: str, pe_id: UUID, *, transfer_code: str | None = "TRF_xyz"
) -> dict[str, object]:
    data: dict[str, object] = {"reference": str(pe_id)}
    if transfer_code is not None:
        data["transfer_code"] = transfer_code
    return {"event": event, "data": data}


async def test_verify_signature() -> None:
    # async only to satisfy the module asyncio mark — no await needed.
    svc = _service(_StubPayments(None), _StubEscrow())
    body = b'{"event":"charge.success"}'
    good = hmac.new(_SECRET.encode(), body, hashlib.sha512).hexdigest()
    assert svc.verify_signature(body, good) is True
    assert svc.verify_signature(body, "deadbeef") is False
    assert svc.verify_signature(body, None) is False


async def test_charge_success_credits_escrow() -> None:
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()
    outcome = await _service(payments, escrow).handle(_charge_success(pe))

    assert outcome == WebhookOutcome.credited
    assert ("completed", str(pe)) in payments.updates
    assert escrow.credits == [_AMOUNT]


async def test_duplicate_webhook_is_noop() -> None:
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe, status="completed")), _StubEscrow()
    outcome = await _service(payments, escrow).handle(_charge_success(pe))

    assert outcome == WebhookOutcome.duplicate
    assert escrow.credits == []  # not credited twice


async def test_amount_mismatch_does_not_credit() -> None:
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()
    outcome = await _service(payments, escrow).handle(_charge_success(pe, amount=123))

    assert outcome == WebhookOutcome.amount_mismatch
    assert escrow.credits == []


async def test_unhandled_event_ignored() -> None:
    outcome = await _service(_StubPayments(None), _StubEscrow()).handle(
        {"event": "subscription.create"}
    )
    assert outcome == WebhookOutcome.ignored


async def test_unknown_reference_ignored() -> None:
    payments, escrow = _StubPayments(None), _StubEscrow()
    outcome = await _service(payments, escrow).handle(_charge_success(uuid4()))
    assert outcome == WebhookOutcome.ignored
    assert escrow.credits == []


# --- transfer (payout) webhooks — SCRUM-145 ---------------------------------


async def test_transfer_success_settles_processing_payout() -> None:
    pe = uuid4()
    payments = _StubPayments(
        _detail(pe_id=pe, status="processing", payment_type="realtor_commission")
    )
    receipts, audit = _StubReceipts(), _StubAudit()
    outcome = await _service(payments, _StubEscrow(), receipts, audit).handle(
        _transfer_event("transfer.success", pe)
    )

    assert outcome == WebhookOutcome.settled
    assert ("completed", "TRF_xyz") in payments.updates
    assert receipts.written == [pe]  # immutable receipt written on settle
    assert "transfer.settled" in audit.actions


async def test_transfer_success_falls_back_to_pe_id_reference() -> None:
    pe = uuid4()
    payments = _StubPayments(
        _detail(pe_id=pe, status="processing", payment_type="seller_disbursement")
    )
    outcome = await _service(payments, _StubEscrow()).handle(
        _transfer_event("transfer.success", pe, transfer_code=None)
    )

    assert outcome == WebhookOutcome.settled
    assert ("completed", str(pe)) in payments.updates


async def test_transfer_success_on_completed_is_duplicate() -> None:
    pe = uuid4()
    payments = _StubPayments(
        _detail(pe_id=pe, status="completed", payment_type="realtor_commission")
    )
    receipts = _StubReceipts()
    outcome = await _service(payments, _StubEscrow(), receipts).handle(
        _transfer_event("transfer.success", pe)
    )

    assert outcome == WebhookOutcome.duplicate
    assert payments.updates == []  # no re-write
    assert receipts.written == []  # no second receipt


async def test_transfer_success_on_failed_is_ignored_not_resurrected() -> None:
    # A late success must never resurrect a payout already marked failed.
    pe = uuid4()
    payments = _StubPayments(_detail(pe_id=pe, status="failed", payment_type="realtor_commission"))
    outcome = await _service(payments, _StubEscrow()).handle(
        _transfer_event("transfer.success", pe)
    )

    assert outcome == WebhookOutcome.ignored
    assert payments.updates == []


async def test_transfer_failed_marks_payout_failed() -> None:
    pe = uuid4()
    payments = _StubPayments(
        _detail(pe_id=pe, status="processing", payment_type="seller_disbursement")
    )
    receipts, audit = _StubReceipts(), _StubAudit()
    outcome = await _service(payments, _StubEscrow(), receipts, audit).handle(
        _transfer_event("transfer.failed", pe)
    )

    assert outcome == WebhookOutcome.failed
    assert ("failed", "TRF_xyz") in payments.updates
    assert receipts.written == []  # no receipt for a failed payout
    assert "transfer.failed" in audit.actions


async def test_transfer_failed_on_failed_is_duplicate() -> None:
    pe = uuid4()
    payments = _StubPayments(_detail(pe_id=pe, status="failed", payment_type="realtor_commission"))
    outcome = await _service(payments, _StubEscrow()).handle(_transfer_event("transfer.failed", pe))

    assert outcome == WebhookOutcome.duplicate
    assert payments.updates == []


async def test_transfer_failed_on_completed_is_ignored() -> None:
    # A settled payout can't be un-settled by a late failure event.
    pe = uuid4()
    payments = _StubPayments(
        _detail(pe_id=pe, status="completed", payment_type="seller_disbursement")
    )
    outcome = await _service(payments, _StubEscrow()).handle(_transfer_event("transfer.failed", pe))

    assert outcome == WebhookOutcome.ignored
    assert payments.updates == []


async def test_transfer_event_for_non_payout_type_ignored() -> None:
    # A transfer event whose reference points at a deposit is not ours to settle.
    pe = uuid4()
    payments = _StubPayments(_detail(pe_id=pe, status="processing", payment_type="buyer_deposit"))
    outcome = await _service(payments, _StubEscrow()).handle(
        _transfer_event("transfer.success", pe)
    )

    assert outcome == WebhookOutcome.ignored
    assert payments.updates == []


async def test_transfer_event_unknown_reference_ignored() -> None:
    outcome = await _service(_StubPayments(None), _StubEscrow()).handle(
        _transfer_event("transfer.success", uuid4())
    )
    assert outcome == WebhookOutcome.ignored


async def test_transfer_event_non_uuid_reference_ignored() -> None:
    outcome = await _service(_StubPayments(None), _StubEscrow()).handle(
        {"event": "transfer.success", "data": {"reference": "not-a-uuid"}}
    )
    assert outcome == WebhookOutcome.ignored


# --------------------------------------------------------------------------
# SCRUM-195 — the seller is told once escrow is actually funded
# --------------------------------------------------------------------------


async def test_seller_is_notified_after_a_deposit_is_credited() -> None:
    pe = uuid4()
    detail = _detail(pe_id=pe)
    payments, escrow = _StubPayments(detail), _StubEscrow()
    txs, sellers = _StubTransactions(), _StubSellers()

    outcome = await _service(payments, escrow, transactions=txs, sellers=sellers).handle(
        _charge_success(pe)
    )

    assert outcome == WebhookOutcome.credited
    assert sellers.calls == [
        {
            "seller_id": txs.seller_id,
            "transaction_id": detail.transaction_id,
            "amount_kobo": _AMOUNT,
        }
    ]


async def test_the_notification_uses_the_server_recorded_amount() -> None:
    """Never the webhook's own figure — the same rule the escrow credit follows."""
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()
    sellers = _StubSellers()

    await _service(payments, escrow, transactions=_StubTransactions(), sellers=sellers).handle(
        _charge_success(pe)
    )

    assert sellers.calls[0]["amount_kobo"] == _AMOUNT


async def test_a_duplicate_webhook_does_not_re_notify() -> None:
    """Paystack retries. A seller must not be told twice that one deposit landed."""
    pe = uuid4()
    payments = _StubPayments(_detail(pe_id=pe, status="completed"))
    sellers = _StubSellers()

    outcome = await _service(
        payments, _StubEscrow(), transactions=_StubTransactions(), sellers=sellers
    ).handle(_charge_success(pe))

    assert outcome == WebhookOutcome.duplicate
    assert sellers.calls == []


async def test_an_amount_mismatch_credits_nothing_and_notifies_nobody() -> None:
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()
    sellers = _StubSellers()
    # The helper takes the amount, so the payload stays typed rather than
    # being mutated through a dict[str, object].
    payload = _charge_success(pe, amount=_AMOUNT + 1)

    outcome = await _service(
        payments, escrow, transactions=_StubTransactions(), sellers=sellers
    ).handle(payload)

    assert outcome == WebhookOutcome.amount_mismatch
    assert escrow.credits == []
    assert sellers.calls == []


async def test_a_broker_outage_does_not_fail_the_webhook() -> None:
    """The credit is already committed. Raising here would make Paystack retry a
    deposit that already succeeded, for the sake of a message."""
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()

    outcome = await _service(
        payments,
        escrow,
        transactions=_StubTransactions(),
        sellers=_StubSellers(raises=True),
    ).handle(_charge_success(pe))

    assert outcome == WebhookOutcome.credited
    assert escrow.credits == [_AMOUNT]


async def test_a_failed_seller_lookup_does_not_fail_the_webhook() -> None:
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()

    outcome = await _service(
        payments,
        escrow,
        transactions=_StubTransactions(raises=True),
        sellers=_StubSellers(),
    ).handle(_charge_success(pe))

    assert outcome == WebhookOutcome.credited
    assert escrow.credits == [_AMOUNT]


async def test_without_a_notifier_the_webhook_still_credits() -> None:
    """Both collaborators are optional, so every construction that predates
    SCRUM-195 keeps working and simply sends nothing."""
    pe = uuid4()
    payments, escrow = _StubPayments(_detail(pe_id=pe)), _StubEscrow()

    outcome = await _service(payments, escrow).handle(_charge_success(pe))

    assert outcome == WebhookOutcome.credited
    assert escrow.credits == [_AMOUNT]
