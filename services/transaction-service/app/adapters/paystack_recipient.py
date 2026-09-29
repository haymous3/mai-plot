"""Paystack transfer-recipient client (SCRUM-145) — payout destination.

A real Paystack transfer must target a `recipient_code`, created once per payee
bank account via POST {base}/transferrecipient. This is the setup step before the
transfer itself (adapters/paystack.py, SCRUM-145 PR2).

  * PaystackRecipientClient — Protocol every call site uses.
  * FakePaystackRecipientClient — synthetic recipient_code, no network. The
    dev/CI/test default so the payout-account flow runs without Paystack.
  * PaystackHttpRecipientClient — real transferrecipient call (behind
    paystack_enabled).

SCRUM-223 adds `resolve_account` — Paystack's GET /bank/resolve — which returns
the name the BANK holds for an account number. The payout form shows it for the
payee to confirm, and PUT /payout-account stores it instead of anything typed,
so a mistyped digit surfaces as "that's not me" rather than a transfer to a
stranger.

Secrets are never logged; the account number is not placed in error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class RecipientResult:
    recipient_code: str


@dataclass(frozen=True)
class ResolvedAccount:
    account_name: str


class PaystackRecipientError(RuntimeError):
    """The recipient rail itself failed (network / provider / logical error)."""


class AccountNotResolved(RuntimeError):
    """The bank does not recognise this account number for this bank code. A
    user-fixable answer, unlike PaystackRecipientError — kept separate so the
    route can say "check the number" rather than "try again later"."""


class PaystackRecipientClient(Protocol):
    async def create_recipient(
        self, *, account_number: str, bank_code: str, account_name: str
    ) -> RecipientResult:  # pragma: no cover - protocol
        ...

    async def resolve_account(
        self, *, account_number: str, bank_code: str
    ) -> ResolvedAccount:  # pragma: no cover - protocol
        ...


FAKE_ACCOUNT_NAME = "MAIHOMME TEST ACCOUNT"


class FakePaystackRecipientClient:
    """In-process fake — returns a synthetic recipient_code derived from the
    account's last 4 digits; never calls the network."""

    async def create_recipient(
        self, *, account_number: str, bank_code: str, account_name: str
    ) -> RecipientResult:
        return RecipientResult(recipient_code=f"RCP_FAKE_{account_number[-4:]}")

    async def resolve_account(self, *, account_number: str, bank_code: str) -> ResolvedAccount:
        # An account number ending 0000 is "unknown to the bank", so the
        # not-found path can be exercised locally and in tests.
        if account_number.endswith("0000"):
            raise AccountNotResolved()
        return ResolvedAccount(account_name=FAKE_ACCOUNT_NAME)


class PaystackHttpRecipientClient:
    """Real Paystack recipient client — POST {base}/transferrecipient (type nuban).

    Every failure maps to PaystackRecipientError so the caller surfaces one error
    type: a non-2xx status, a network/timeout, a non-JSON body, Paystack's own
    `200 {status:false}`, or a success body missing `recipient_code`. The secret
    key is a bearer header and never appears in an error message.

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

    async def create_recipient(
        self, *, account_number: str, bank_code: str, account_name: str
    ) -> RecipientResult:
        payload = {
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN",
        }
        try:
            async with httpx.AsyncClient(timeout=15, transport=self._transport) as client:
                resp = await client.post(
                    f"{self._base_url}/transferrecipient",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            # Network, timeout, and non-2xx all land here. str(HTTPError) is the
            # status + URL — never the Authorization header or the account number.
            raise PaystackRecipientError(f"paystack recipient request failed: {exc}") from exc
        except ValueError as exc:  # resp.json() on a non-JSON body
            raise PaystackRecipientError("paystack recipient returned a non-JSON body") from exc

        if not body.get("status"):
            raise PaystackRecipientError(
                f"paystack declined the recipient: {body.get('message', 'unknown error')}"
            )
        data = body.get("data") or {}
        recipient_code = data.get("recipient_code")
        if not recipient_code:
            raise PaystackRecipientError("paystack recipient response missing recipient_code")
        return RecipientResult(recipient_code=recipient_code)

    async def resolve_account(self, *, account_number: str, bank_code: str) -> ResolvedAccount:
        """GET {base}/bank/resolve. Paystack answers 422 (or 400) with
        `status:false` when the number does not exist at that bank — that is
        AccountNotResolved. Everything else that goes wrong is the rail's fault
        and maps to PaystackRecipientError, as in create_recipient."""
        try:
            async with httpx.AsyncClient(timeout=15, transport=self._transport) as client:
                resp = await client.get(
                    f"{self._base_url}/bank/resolve",
                    params={"account_number": account_number, "bank_code": bank_code},
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
        except httpx.HTTPError as exc:
            raise PaystackRecipientError(f"paystack resolve request failed: {exc}") from exc
        if resp.status_code in (400, 422):
            raise AccountNotResolved()
        try:
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise PaystackRecipientError(f"paystack resolve request failed: {exc}") from exc
        except ValueError as exc:
            raise PaystackRecipientError("paystack resolve returned a non-JSON body") from exc
        if not body.get("status"):
            raise AccountNotResolved()
        name = ((body.get("data") or {}).get("account_name") or "").strip()
        if not name:
            raise PaystackRecipientError("paystack resolve response missing account_name")
        return ResolvedAccount(account_name=name)


def build_paystack_recipient_client(
    *, enabled: bool, secret_key: str, base_url: str
) -> PaystackRecipientClient:
    if enabled:
        return PaystackHttpRecipientClient(secret_key=secret_key, base_url=base_url)
    return FakePaystackRecipientClient()
