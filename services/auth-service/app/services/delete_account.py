"""Account deletion (SCRUM-188).

SOFT delete, chosen by the product owner. `deleted_at` is set and the account
stops authenticating, but transactions, escrow movements, commissions and audit
rows all survive — CBN and AMLON require the financial trail to outlive the
account that created it (CLAUDE.md §9).

Migrations 0009 and 0010 already made a soft delete release the user's phone
and email: both unique constraints are partial indexes over live rows. So a
deleted user's identifiers become available for re-registration with no extra
work here. This service is the first thing in the codebase that actually WRITES
`deleted_at` — the two migrations built the schema support ahead of it.

The profile photo IS really deleted from S3, unlike the rest. A face photo has
no retention basis the way the ledger does, so NDPR erasure wins for that one
artefact (see `UserRepository.soft_delete`).
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.deals import DealChecker, DealCheckUnavailable
from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


class DeleteAccountError(RuntimeError):
    pass


class AccountHasActiveDeals(DeleteAccountError):
    """The caller is still a party to a non-terminal transaction."""


class DeleteCheckUnavailable(DeleteAccountError):
    """The active-deal guard could not be evaluated, so deletion is refused."""


class AccountAlreadyGone(DeleteAccountError):
    """No live account for this id — already deleted, or never existed."""


class DeleteAccountService:
    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        deals: DealChecker,
        storage: DocumentStorage,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._deals = deals
        self._storage = storage

    async def delete(self, *, user_id: UUID, bearer_token: str) -> None:
        """Soft-delete the caller's account.

        The guard runs BEFORE any write, and an unavailable guard refuses the
        request rather than assuming the user is clear — see the fail-closed
        note in `adapters/deals.py`.
        """
        try:
            if await self._deals.has_active_deals(bearer_token=bearer_token):
                raise AccountHasActiveDeals()
        except DealCheckUnavailable as exc:
            raise DeleteCheckUnavailable() from exc

        deleted, avatar_key = await self._users.soft_delete(user_id)
        if not deleted:
            raise AccountAlreadyGone()

        # Revoking every refresh token stops any session being RENEWED. It does
        # not invalidate the access token already in the caller's hands — that
        # stays signature-valid until it expires. What actually shuts the
        # account out immediately is `deleted_at`: every read goes through
        # get_active_by_id/get_account, which filter it, so an outstanding
        # token resolves to "no such account" (404) rather than to data.
        await self._refresh_tokens.revoke_all_for_user(user_id)

        if avatar_key is not None:
            try:
                await self._storage.delete(avatar_key)
            except DocumentStorageError:
                # The row no longer references it, so the account is deleted
                # either way. Log the orphan for the lifecycle sweep rather
                # than failing a deletion the user already committed to.
                logger.warning("orphaned avatar after deletion of user %s", user_id)
