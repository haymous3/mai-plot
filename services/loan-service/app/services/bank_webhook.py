"""Bank webhook dispatcher (SCRUM-77).

One public endpoint (/webhooks/bank) receives every bank-partner event. This
verifies the HMAC-SHA256 signature over the raw body once, then dispatches by
event to the right handler:

  * loan.decision_ready  → LoanDecisionWebhookService (SCRUM-76)
  * repayment.milestone  → LoanRepaymentWebhookService.handle_milestone
  * loan.fully_repaid    → LoanRepaymentWebhookService.handle_fully_repaid
  * account.opened       → LoanDisbursementWebhookService.handle_account_opened (SCRUM-129)
  * loan.disbursed       → LoanDisbursementWebhookService.handle_disbursed (SCRUM-129)

Unknown events return "ignored" (HTTP 200) so the bank doesn't retry a no-op.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.services.loan_decision import LoanDecisionWebhookService
from app.services.loan_disbursement_webhook import LoanDisbursementWebhookService
from app.services.loan_repayment import LoanRepaymentWebhookService


class BankWebhookDispatcher:
    def __init__(
        self,
        *,
        secret: str,
        decision: LoanDecisionWebhookService,
        repayment: LoanRepaymentWebhookService,
        disbursement: LoanDisbursementWebhookService,
    ) -> None:
        self._secret = secret
        self._decision = decision
        self._repayment = repayment
        self._disbursement = disbursement

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """HMAC-SHA256 of the raw body, constant-time compared to the header."""
        if not signature:
            return False
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle(self, payload: dict[str, Any]) -> str:
        event = payload.get("event")
        if event == "loan.decision_ready":
            return (await self._decision.handle(payload)).value
        if event == "repayment.milestone":
            return (await self._repayment.handle_milestone(payload)).value
        if event == "loan.fully_repaid":
            return (await self._repayment.handle_fully_repaid(payload)).value
        if event == "account.opened":
            return (await self._disbursement.handle_account_opened(payload)).value
        if event == "loan.disbursed":
            return (await self._disbursement.handle_disbursed(payload)).value
        return "ignored"
