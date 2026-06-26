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
    """Real Paystack charge client — POST {base}/transaction/initialize."""

    def __init__(self, *, secret_key: str, base_url: str) -> None:
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")

    async def initialize(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str | None
    ) -> CheckoutInit:  # pragma: no cover - unbuilt without a real account
        import httpx

        payload: dict[str, object] = {
            "reference": reference,
            "amount": amount_kobo,  # Paystack NGN amounts are in kobo
            "email": email,
        }
        if callback_url:
            payload["callback_url"] = callback_url
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self._base_url}/transaction/initialize",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
            resp.raise_for_status()
            data = resp.json()["data"]
        except Exception as exc:  # httpx/HTTP/parse errors
            raise PaystackChargeError(str(exc)) from exc
        return CheckoutInit(
            authorization_url=data["authorization_url"],
            reference=data.get("reference", reference),
        )


def build_paystack_charge_client(
    *, enabled: bool, secret_key: str, base_url: str
) -> PaystackChargeClient:
    if enabled:
        return PaystackHttpChargeClient(secret_key=secret_key, base_url=base_url)
    return FakePaystackChargeClient()
