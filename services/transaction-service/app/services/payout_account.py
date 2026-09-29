"""Payout-account management (SCRUM-145, hardened in SCRUM-223).

A payee (realtor / seller) registers the bank account they want to be paid into.
Setting an account creates its Paystack transfer recipient up front (so the later
payout just references the recipient_code) and stores both. No money moves here.

SCRUM-223 — where a payout can go is guarded, because redirecting it is the
whole prize for anyone holding a stolen session:

  * The account NAME comes from the bank (Paystack /bank/resolve), never from the
    request. The payee sees it and confirms "that's me" before saving, so a
    mistyped number is caught instead of paid out to a stranger.
  * Saving requires a fresh password re-entry (a reauth token, checked by the
    route — see routes/payout_accounts.py).
  * Every change is audited and emailed to the account holder, past any opt-out.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.paystack_recipient import PaystackRecipientClient
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.payout_account_repo import PayoutAccountRepository, PayoutAccountRow
from app.services.payout_notifier import PayoutNotifier

logger = logging.getLogger(__name__)


class PayoutAccountService:
    def __init__(
        self,
        *,
        accounts: PayoutAccountRepository,
        recipient_client: PaystackRecipientClient,
        audit: AuditLogRepository,
        notifier: PayoutNotifier,
    ) -> None:
        self._accounts = accounts
        self._recipient_client = recipient_client
        self._audit = audit
        self._notifier = notifier

    async def resolve_name(self, *, account_number: str, bank_code: str) -> str:
        """The name the bank holds for this account. AccountNotResolved when the
        bank does not know it; PaystackRecipientError when the rail fails."""
        resolved = await self._recipient_client.resolve_account(
            account_number=account_number, bank_code=bank_code
        )
        return resolved.account_name

    async def set_account(
        self,
        *,
        user_id: UUID,
        actor_role: str,
        account_number: str,
        bank_code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PayoutAccountRow:
        """Register/replace the caller's payout account.

        Resolves the name with the bank FIRST (so the stored name is the bank's),
        then creates the Paystack transfer recipient, then persists. Provider
        errors bubble up for the route to translate; nothing is written until
        both provider calls have succeeded.
        """
        account_name = await self.resolve_name(account_number=account_number, bank_code=bank_code)
        previous = await self._accounts.get(user_id)
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
        await self._audit.record(
            actor_id=user_id,
            actor_role=actor_role,
            action="payout_account.updated",
            entity_type="payout_account",
            entity_id=row.id,
            # Bank + last four only: the audit trail is read by admins and must
            # not become a place full account numbers can be collected from.
            old_value=_summary(previous),
            new_value=_summary(row),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._notifier.account_changed(
            user_id=user_id, account_last4=account_number[-4:], first_time=previous is None
        )
        logger.info(
            "payout_account.set", extra={"user_id": str(user_id), "first": previous is None}
        )
        return row

    async def get_account(self, user_id: UUID) -> PayoutAccountRow | None:
        return await self._accounts.get(user_id)


def _summary(row: PayoutAccountRow | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {"bank_code": row.bank_code, "account_last4": row.account_number[-4:]}
