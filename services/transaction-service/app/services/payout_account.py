"""Payout-account management (SCRUM-145).

A payee (realtor / seller) registers the bank account they want to be paid into.
Setting an account creates its Paystack transfer recipient up front (so the later
payout just references the recipient_code) and stores both. No money moves here.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.paystack_recipient import PaystackRecipientClient
from app.repositories.payout_account_repo import PayoutAccountRepository, PayoutAccountRow

logger = logging.getLogger(__name__)


class PayoutAccountService:
    def __init__(
        self,
        *,
        accounts: PayoutAccountRepository,
        recipient_client: PaystackRecipientClient,
    ) -> None:
        self._accounts = accounts
        self._recipient_client = recipient_client

    async def set_account(
        self, *, user_id: UUID, account_number: str, bank_code: str, account_name: str
    ) -> PayoutAccountRow:
        """Register/replace the caller's payout account. Creates the Paystack
        transfer recipient first (PaystackRecipientError bubbles up so the route
        can 503), then persists the account + recipient_code."""
        recipient = await self._recipient_client.create_recipient(
            account_number=account_number, bank_code=bank_code, account_name=account_name
        )
        row = await self._accounts.upsert(
            user_id=user_id,
            account_number=account_number,
            bank_code=bank_code,
            account_name=account_name,
            recipient_code=recipient.recipient_code,
        )
        logger.info("payout_account.set", extra={"user_id": str(user_id)})
        return row

    async def get_account(self, user_id: UUID) -> PayoutAccountRow | None:
        return await self._accounts.get(user_id)
