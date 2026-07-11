"""Access to payout_accounts (SCRUM-145).

Where a payee (realtor / seller) is paid: their NUBAN bank account + the Paystack
transfer recipient_code created for it. One row per user (user_id UNIQUE). No
balances, no money movement — this only records the destination for a payout.
account_number is financial PII; callers must mask it before returning/logging.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PayoutAccountRow:
    id: UUID
    user_id: UUID
    account_number: str
    bank_code: str
    account_name: str
    recipient_code: str | None


class PayoutAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> PayoutAccountRow | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT id, user_id, account_number, bank_code, account_name, recipient_code "
                    "FROM payout_accounts WHERE user_id = :uid AND deleted_at IS NULL"
                ),
                {"uid": user_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def upsert(
        self,
        *,
        user_id: UUID,
        account_number: str,
        bank_code: str,
        account_name: str,
        recipient_code: str | None,
    ) -> PayoutAccountRow:
        """Set (or replace) the user's payout account. Changing bank details mints
        a fresh recipient_code, so the whole row is overwritten and any prior
        soft-delete is cleared."""
        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO payout_accounts
                        (user_id, account_number, bank_code, account_name, recipient_code)
                    VALUES (:uid, :acct, :bank, :name, :rcp)
                    ON CONFLICT (user_id) DO UPDATE SET
                        account_number = EXCLUDED.account_number,
                        bank_code = EXCLUDED.bank_code,
                        account_name = EXCLUDED.account_name,
                        recipient_code = EXCLUDED.recipient_code,
                        deleted_at = NULL,
                        updated_at = NOW()
                    RETURNING id, user_id, account_number, bank_code, account_name, recipient_code
                    """
                ),
                {
                    "uid": user_id,
                    "acct": account_number,
                    "bank": bank_code,
                    "name": account_name,
                    "rcp": recipient_code,
                },
            )
        ).one()
        return self._to_row(row)

    @staticmethod
    def _to_row(r: object) -> PayoutAccountRow:
        return PayoutAccountRow(
            id=r.id,  # type: ignore[attr-defined]
            user_id=r.user_id,  # type: ignore[attr-defined]
            account_number=r.account_number,  # type: ignore[attr-defined]
            bank_code=r.bank_code,  # type: ignore[attr-defined]
            account_name=r.account_name,  # type: ignore[attr-defined]
            recipient_code=r.recipient_code,  # type: ignore[attr-defined]
        )
