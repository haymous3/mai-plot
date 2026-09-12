"""Admin NIN console (SCRUM-224): read, reveal, set/replace and clear a
user's NIN.

Until this ticket the NIN was write-once and one-way: a user verified it
during onboarding, it was bcrypt-hashed, and nobody — not the user, not an
admin — could ever see it again or change it. That is what §4 asked for, and
it left three real jobs with no tool: a support agent confirming identity on
a call, a regulator or bank partner asking for a specific user's NIN under
AMLON/KYC, and a user who typed the wrong number at registration and is now
stuck (`/auth/verify/nin` is single-use per account). The product owner has
accepted the deviation: the NIN is now stored AES-256-GCM encrypted as well
(services/nin_crypto.py) and this service is the only reader.

What protects the value now
---------------------------
  * `require_admin` on every route — admin JWT AND the IP allowlist (§4).
  * A **reveal is a POST with a mandatory reason**, and writes an audit row
    naming the admin, the user, the reason and the last four digits. Reading
    the number is an act, not a view; the audit log is how a regulator later
    learns who looked and why. The plain GET returns only the last four.
  * **Set / replace re-verifies with the registry** — the same Ninja call and
    the same name match as the user's own path. An admin cannot put a NIN on
    file that the registry did not confirm, and each attempt costs the same
    ~₦100 the user's does.
  * **One NIN, one account.** The HMAC dedup still runs; a number that another
    live account owns is refused with 409 rather than moved.
  * **Clear walks verified_status back** (see `UserRepository.clear_nin`) so a
    cleared account cannot keep reading as id-verified.
  * The number is never logged. Audit payloads and log lines carry `last4`
    only; the full value exists in exactly one place: the reveal response.

Pre-migration rows
------------------
A NIN verified before migration 0016 has a hash but no ciphertext. The GET
reports it as `recoverable: false`; a reveal answers 409 NIN_NOT_RECOVERABLE.
The admin's remedy is Replace, which re-verifies and stores a recoverable
copy. There is no other way back — bcrypt is one-way by design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.adapters.nin import NinVerificationError, NinVerifier
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import NinRecord, UserRepository
from app.security import CurrentUser
from app.services.nin import hash_nin, lookup_nin, split_full_name, validate_nin_format
from app.services.nin_crypto import NinCipher, NinDecryptError

logger = logging.getLogger(__name__)


class AdminNinError(RuntimeError):
    pass


class UserNotFound(AdminNinError):
    pass


class UserDeleted(AdminNinError):
    """Set and clear refuse on a soft-deleted account; reveal does not."""


class NinNotOnFile(AdminNinError):
    pass


class NinNotRecoverable(AdminNinError):
    """Verified before migration 0016: hash only, nothing to decrypt."""


class NinBelongsToAnotherAccount(AdminNinError):
    pass


class NinHeldByLinkedAccount(AdminNinError):
    """This row is a linked second account (SCRUM-225); the NIN lives on its
    root. Reveal, set and clear are refused here ON PURPOSE (SCRUM-229):

    * the reveal audit (`user.nin_revealed_by_admin`) must be written against
      the account that actually HOLDS the number, or a regulator reading the
      trail sees a reveal on a row that carries no NIN;
    * exactly one row owns a NIN — the UNIQUE index enforces it and the whole
      linking model rests on it — and writing through a sibling would blur that.

    The admin manages the NIN on the root, which `held_by` names.
    """

    def __init__(self, held_by: UUID) -> None:
        super().__init__(str(held_by))
        self.held_by = held_by


class NinRejectedByRegistry(AdminNinError):
    """Ninja answered but did not confirm the number (or the name mismatched)."""

    def __init__(self, status: str, mismatches: tuple[str, ...]) -> None:
        super().__init__(status)
        self.status = status
        self.mismatches = mismatches


class NinRegistryUnavailable(AdminNinError):
    """The registry call failed (network/5xx) — retryable."""


@dataclass(frozen=True)
class NinStatus:
    nin_verified: bool
    nin_last4: str | None
    nin_verified_at: datetime | None
    recoverable: bool
    # The root account when this one is a linked second account (SCRUM-229).
    # Everything above then describes the ROOT's NIN, and the console shows a
    # pointer to it in place of the reveal/set/clear controls.
    held_by_user_id: UUID | None = None

    @classmethod
    def from_record(cls, record: NinRecord) -> NinStatus:
        return cls(
            nin_verified=record.has_nin,
            nin_last4=record.nin_last4,
            nin_verified_at=record.nin_verified_at,
            # From the record's own flag, NOT `nin_encrypted is not None`: a
            # linked account's record never carries the ciphertext.
            recoverable=record.recoverable,
            held_by_user_id=record.held_by_user_id,
        )


class AdminNinService:
    def __init__(
        self,
        *,
        users: UserRepository,
        audit: AuditLogRepository,
        verifier: NinVerifier,
        cipher: NinCipher,
        pepper: str,
    ) -> None:
        self._users = users
        self._audit = audit
        self._verifier = verifier
        self._cipher = cipher
        self._pepper = pepper

    async def get_status(self, *, user_id: UUID) -> NinStatus:
        """Masked view: verified?, last four, when, and whether a reveal would
        work. Not separately audited — it is loaded with the user detail page,
        whose read already writes `user.viewed_by_admin`, and it carries no
        more than the detail's `nin_verified` plus four digits."""
        record = await self._users.get_nin_record(user_id)
        if record is None:
            raise UserNotFound()
        return NinStatus.from_record(record)

    async def reveal(
        self,
        *,
        user_id: UUID,
        admin: CurrentUser,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """Decrypt and return the NIN. The audit row is written in the same
        transaction as the read — there is no code path that returns the
        number without recording who asked and why."""
        record = await self._users.get_nin_record(user_id)
        if record is None:
            raise UserNotFound()
        # Before anything else: a sibling's record carries no ciphertext by
        # construction, so this is the guard that gives the admin a useful
        # answer rather than a misleading "not recoverable".
        if record.held_by_user_id is not None:
            raise NinHeldByLinkedAccount(record.held_by_user_id)
        if not record.has_nin:
            raise NinNotOnFile()
        if record.nin_encrypted is None:
            raise NinNotRecoverable()
        try:
            nin = self._cipher.decrypt(record.nin_encrypted, user_id=user_id)
        except NinDecryptError:
            # A ciphertext that will not open under the configured key is an
            # operations problem (rotated key, wrong environment), not a
            # "nothing on file" — say so, and log without the value.
            logger.error("admin.nin.decrypt_failed", extra={"user_id": str(user_id)})
            raise NinNotRecoverable() from None
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.nin_revealed_by_admin",
            entity_type="user",
            entity_id=user_id,
            new_value={"reason": reason, "nin_last4": record.nin_last4},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("admin.nin.revealed", extra={"user_id": str(user_id)})
        return nin

    async def set_nin(
        self,
        *,
        user_id: UUID,
        admin: CurrentUser,
        nin: str,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NinStatus:
        """Create or replace. Same registry check as the user's own path; the
        difference is that an existing NIN on THIS account is overwritten
        rather than refused, because correcting one is the point."""
        validate_nin_format(nin)  # InvalidNinError -> 422, value never echoed
        record = await self._users.get_nin_record(user_id)
        if record is None:
            raise UserNotFound()
        if record.deleted_at is not None:
            raise UserDeleted()
        # Writing a NIN onto a sibling could only ever collide with the root's
        # under idx_user_pii_nin_lookup. Say so, and say where to go instead.
        if record.held_by_user_id is not None:
            raise NinHeldByLinkedAccount(record.held_by_user_id)

        lookup = lookup_nin(nin, pepper=self._pepper)
        owner = await self._users.find_user_by_nin_lookup(lookup)
        if owner is not None and owner != user_id:
            raise NinBelongsToAnotherAccount()

        account = await self._users.get_account(user_id)
        first, last = (
            split_full_name(account.full_name)
            if account is not None and account.full_name.strip()
            else (None, None)
        )
        try:
            outcome = await self._verifier.verify(nin, first_name=first, last_name=last)
        except NinVerificationError as exc:
            logger.error("admin.nin.registry_unavailable", extra={"user_id": str(user_id)})
            raise NinRegistryUnavailable() from exc
        if outcome.status != "verified":
            logger.info(
                "admin.nin.not_verified",
                extra={
                    "user_id": str(user_id),
                    "status": outcome.status,
                    "mismatches": list(outcome.mismatches),
                },
            )
            raise NinRejectedByRegistry(outcome.status, outcome.mismatches)

        await self._users.set_nin_verified(
            user_id,
            nin_hash=hash_nin(nin),
            nin_lookup=lookup,
            nin_encrypted=self._cipher.encrypt(nin, user_id=user_id),
            nin_last4=nin[-4:],
        )
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.nin_set_by_admin",
            entity_type="user",
            entity_id=user_id,
            old_value={"nin_verified": record.has_nin, "nin_last4": record.nin_last4},
            new_value={"nin_verified": True, "nin_last4": nin[-4:], "reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("admin.nin.set", extra={"user_id": str(user_id)})
        after = await self._users.get_nin_record(user_id)
        assert after is not None  # the row was just written
        return NinStatus.from_record(after)

    async def clear_nin(
        self,
        *,
        user_id: UUID,
        admin: CurrentUser,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NinStatus:
        """Remove the NIN and walk verified_status back. The user can then
        verify again through onboarding, or the admin can set a new one."""
        record = await self._users.get_nin_record(user_id)
        if record is None:
            raise UserNotFound()
        if record.deleted_at is not None:
            raise UserDeleted()
        # There is nothing on this row to clear; the NIN is the root's.
        if record.held_by_user_id is not None:
            raise NinHeldByLinkedAccount(record.held_by_user_id)
        if not record.has_nin:
            raise NinNotOnFile()

        if not await self._users.clear_nin(user_id):
            raise UserNotFound()
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.nin_cleared_by_admin",
            entity_type="user",
            entity_id=user_id,
            old_value={"nin_verified": True, "nin_last4": record.nin_last4},
            new_value={"nin_verified": False, "reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("admin.nin.cleared", extra={"user_id": str(user_id)})
        after = await self._users.get_nin_record(user_id)
        assert after is not None
        return NinStatus.from_record(after)
