"""Bank webhook dispatcher (SCRUM-77).

One public endpoint (/webhooks/bank) receives every bank-partner event. This
verifies the HMAC-SHA256 signature over the raw body once, then dispatches by
event to the right handler:

  * loan.decision_ready  → LoanDecisionWebhookService (SCRUM-76)
  * repayment.milestone  → LoanRepaymentWebhookService.handle_milestone
  * loan.fully_repaid    → LoanRepaymentWebhookService.handle_fully_repaid

Unknown events return "ignored" (HTTP 200) so the bank doesn't retry a no-op.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.services.loan_decision import LoanDecisionWebhookService
from app.services.loan_repayment import LoanRepaymentWebhookService


class BankWebhookDispatcher:
    def __init__(
        self,
        *,
        secret: str,
        decision: LoanDecisionWebhookService,
        repayment: LoanRepaymentWebhookService,
    ) -> None:
        self._secret = secret
        self._decision = decision
        self._repayment = repayment

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
        return "ignored"
