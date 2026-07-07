"""Paystack charge/collection client (SCRUM-83) — buyer escrow deposit.

Initialises a Paystack transaction and returns the hosted checkout URL. Distinct
from the payout/transfer client (SCRUM-86): this is the inbound collection side.

  * PaystackChargeClient — Protocol every call site uses.
  * FakePaystackChargeClient — synthetic checkout URL, no network. The dev/CI/test
    default so the deposit flow runs without Paystack.
  * PaystackHttpChargeClient — real `transaction/initialize` (deferred to a real
    Paystack account; behind paystack_enabled).

Amounts are BIGINT kobo (CLAUDE.md). Secrets are never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class CheckoutInit:
    authorization_url: str
    reference: str


class PaystackChargeError(RuntimeError):
    """The charge rail itself failed (network / provider error)."""


class PaystackChargeClient(Protocol):
    async def initialize(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str | None
    ) -> CheckoutInit:  # pragma: no cover - protocol
        ...


class FakePaystackChargeClient:
    """In-process fake — returns a synthetic hosted-checkout URL for the given
    reference; never calls the network."""

    async def initialize(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str | None
    ) -> CheckoutInit:
        return CheckoutInit(
            authorization_url=f"https://checkout.paystack.test/pay/{reference}",
            reference=reference,
        )


class PaystackHttpChargeClient:
    """Real Paystack charge client — POST {base}/transaction/initialize.

    Every failure mode maps to PaystackChargeError so the deposit flow surfaces
    one error type: a non-2xx HTTP status, a network/timeout error, a non-JSON
    body, Paystack's own `200 {status:false}` logical rejection, or a success
    body missing `authorization_url`. The secret key is sent as a bearer header
    and never placed in an error message.

    `transport` is an injection seam for unit tests (an httpx.MockTransport);
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

    async def initialize(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str | None
    ) -> CheckoutInit:
        payload: dict[str, object] = {
            "reference": reference,
            "amount": amount_kobo,  # Paystack NGN amounts are in kobo
            "email": email,
        }
        if callback_url:
            payload["callback_url"] = callback_url
        try:
            async with httpx.AsyncClient(timeout=15, transport=self._transport) as client:
                resp = await client.post(
                    f"{self._base_url}/transaction/initialize",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            # Network, timeout, and non-2xx (raise_for_status) all land here. The
            # str(HTTPError) is status + URL — never the Authorization header.
            raise PaystackChargeError(f"paystack charge request failed: {exc}") from exc
        except ValueError as exc:  # resp.json() on a non-JSON body
            raise PaystackChargeError("paystack charge returned a non-JSON body") from exc

        if not body.get("status"):
            # Paystack signals logical failures with HTTP 200 + status:false.
            raise PaystackChargeError(
                f"paystack declined the charge: {body.get('message', 'unknown error')}"
            )
        data = body.get("data") or {}
        authorization_url = data.get("authorization_url")
        if not authorization_url:
            raise PaystackChargeError("paystack charge response missing authorization_url")
        return CheckoutInit(
            authorization_url=authorization_url,
            reference=data.get("reference", reference),
        )


def build_paystack_charge_client(
    *, enabled: bool, secret_key: str, base_url: str
) -> PaystackChargeClient:
    if enabled:
        return PaystackHttpChargeClient(secret_key=secret_key, base_url=base_url)
    return FakePaystackChargeClient()
