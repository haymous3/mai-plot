"""Paystack transfer (payout) client (SCRUM-86 seam; real impl SCRUM-145).

Sends money OUT of the platform balance to a payee's transfer recipient. A real
Paystack transfer is asynchronous: POST /transfer returns status 'pending' (or
'otp'/'queued') and the final outcome arrives via a transfer.success /
transfer.failed webhook (handled in SCRUM-145 PR3). Only the fake completes
synchronously.

  * PaystackTransferClient — Protocol every call site uses.
  * FakePaystackTransferClient — synthetic synchronous success, no network. The
    dev/CI/test default so the disbursement flow runs end-to-end without Paystack.
  * PaystackHttpTransferClient — real POST /transfer (behind paystack_enabled).

The caller resolves the payee's recipient_code (from payout_accounts) and passes
it in — the HTTP adapter does no DB work. Amounts are BIGINT kobo (CLAUDE.md).
Never logs secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

# Paystack transfer.data.status values, bucketed into what the disbursement flow
# cares about: settled now, in-flight (finish via webhook), or rejected.
TransferStatus = Literal["success", "pending", "failed"]

_PENDING_STATES = frozenset({"pending", "otp", "queued", "processing", "ongoing", "received"})


@dataclass(frozen=True)
class TransferResult:
    reference: str
    status: TransferStatus


class PaystackTransferError(RuntimeError):
    """The transfer rail itself failed (network / provider error)."""


class PaystackTransferClient(Protocol):
    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_code: str
    ) -> TransferResult:  # pragma: no cover - protocol
        ...


class FakePaystackTransferClient:
    """In-process fake — always succeeds synchronously with a synthetic
    reference (no webhook needed)."""

    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_code: str
    ) -> TransferResult:
        return TransferResult(reference=f"FAKE-PSTK-{reference_hint}", status="success")


class PaystackHttpTransferClient:
    """Real Paystack payout client — POST {base}/transfer to a recipient_code.

    Every failure maps to PaystackTransferError so the caller surfaces one error
    type: a non-2xx status, a network/timeout, a non-JSON body, or Paystack's own
    `200 {status:false}`. The transfer itself is async: a `200 {status:true}` with
    data.status in the pending set returns TransferStatus 'pending' and is
    finalised by the transfer webhook; 'success' is an immediate settle; anything
    else is 'failed'. The secret key is a bearer header, never in an error string.

    `transport` is an injection seam for unit tests (httpx.MockTransport);
    production leaves it None so httpx uses the real network transport.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_code: str
    ) -> TransferResult:
        payload = {
            "source": "balance",
            "amount": amount_kobo,  # Paystack NGN amounts are in kobo
            "recipient": recipient_code,
            "reference": reference_hint,
        }
        try:
            async with httpx.AsyncClient(timeout=15, transport=self._transport) as client:
                resp = await client.post(
                    f"{self._base_url}/transfer",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            # Network, timeout, and non-2xx all land here. str(HTTPError) is the
            # status + URL — never the Authorization header.
            raise PaystackTransferError(f"paystack transfer request failed: {exc}") from exc
        except ValueError as exc:  # resp.json() on a non-JSON body
            raise PaystackTransferError("paystack transfer returned a non-JSON body") from exc

        if not body.get("status"):
            raise PaystackTransferError(
                f"paystack declined the transfer: {body.get('message', 'unknown error')}"
            )
        data = body.get("data") or {}
        provider_status = str(data.get("status", "")).lower()
        # transfer_code is Paystack's handle for the async transfer; fall back to
        # our own reference so provider_reference is always set.
        reference = data.get("transfer_code") or reference_hint
        if provider_status == "success":
            return TransferResult(reference=reference, status="success")
        if provider_status in _PENDING_STATES:
            return TransferResult(reference=reference, status="pending")
        return TransferResult(reference=reference, status="failed")


def build_paystack_transfer_client(
    *, enabled: bool, secret_key: str, base_url: str
) -> PaystackTransferClient:
    if enabled:
        return PaystackHttpTransferClient(secret_key=secret_key, base_url=base_url)
    return FakePaystackTransferClient()
