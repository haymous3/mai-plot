"""Unit tests for PaystackWebhookService (SCRUM-83)."""

from __future__ import annotations

import hashlib
import hmac
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
    async def record(self, **kwargs: object) -> None:
        return None


def _detail(*, pe_id: UUID, status: str = "initiated") -> PaymentEventDetail:
    return PaymentEventDetail(
        id=pe_id,
        status=status,
        payment_type="buyer_deposit",
        amount_kobo=_AMOUNT,
        transaction_id=uuid4(),
        payer_id=uuid4(),
    )


def _service(payments: _StubPayments, escrow: _StubEscrow) -> PaystackWebhookService:
    return PaystackWebhookService(
        payments=payments,  # type: ignore[arg-type]
        escrow=escrow,  # type: ignore[arg-type]
        audit=_StubAudit(),  # type: ignore[arg-type]
        secret=_SECRET,
    )


def _charge_success(pe_id: UUID, amount: int = _AMOUNT) -> dict[str, object]:
    return {"event": "charge.success", "data": {"reference": str(pe_id), "amount": amount}}


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


async def test_non_charge_event_ignored() -> None:
    outcome = await _service(_StubPayments(None), _StubEscrow()).handle(
        {"event": "transfer.success"}
    )
    assert outcome == WebhookOutcome.ignored


async def test_unknown_reference_ignored() -> None:
    payments, escrow = _StubPayments(None), _StubEscrow()
    outcome = await _service(payments, escrow).handle(_charge_success(uuid4()))
    assert outcome == WebhookOutcome.ignored
    assert escrow.credits == []
