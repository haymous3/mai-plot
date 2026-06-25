"""Paystack transfer (payout) client (SCRUM-86).

The real Paystack integration is unbuilt (SCRUM-83 / M3). This defines the seam
the disbursement flow depends on:
  * PaystackTransferClient — Protocol every call site uses.
  * FakePaystackTransferClient — synthetic success, no network. The dev/CI/test
    default so the disbursement flow runs end-to-end without Paystack.
  * PaystackHttpTransferClient — placeholder for the real impl (SCRUM-83).

Money amounts are BIGINT kobo (CLAUDE.md). Never logs secrets or full PANs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TransferResult:
    reference: str
    status: str  # 'success' | 'failed'


class PaystackTransferError(RuntimeError):
    """The transfer rail itself failed (network / provider error)."""


class PaystackTransferClient(Protocol):
    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_id: UUID
    ) -> TransferResult:  # pragma: no cover - protocol
        ...


class FakePaystackTransferClient:
    """In-process fake — always succeeds with a synthetic reference."""

    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_id: UUID
    ) -> TransferResult:
        return TransferResult(reference=f"FAKE-PSTK-{reference_hint}", status="success")


class PaystackHttpTransferClient:
    """Real Paystack payout client — deferred to SCRUM-83."""

    def __init__(self, *, secret_key: str) -> None:
        self._secret_key = secret_key

    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_id: UUID
    ) -> TransferResult:  # pragma: no cover - unbuilt
        raise NotImplementedError("Real Paystack transfers land in SCRUM-83 (M3).")


def build_paystack_transfer_client(*, enabled: bool, secret_key: str) -> PaystackTransferClient:
    if enabled:
        return PaystackHttpTransferClient(secret_key=secret_key)
    return FakePaystackTransferClient()
