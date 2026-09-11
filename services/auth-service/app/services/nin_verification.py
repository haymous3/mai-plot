"""NIN verification orchestration.

Ungated since SCRUM-189 — see the note in `verify` for why. Since SCRUM-218 the
check is a real registry MATCH rather than a bare existence lookup: the NIN is
scored against the account holder's name, so submitting a valid NIN that
belongs to somebody else no longer passes.

The plaintext NIN never leaves this call or reaches a log, broker, or the
database — only the bcrypt hash and the HMAC lookup are persisted. Names are
matched but never logged; only the NAMES of mismatched fields are.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.nin import NinVerificationError, NinVerifier
from app.repositories.user_repo import UserRepository
from app.services.nin import hash_nin, lookup_nin, split_full_name, validate_nin_format
from app.services.nin_crypto import NinCipher

logger = logging.getLogger(__name__)


class NinError(RuntimeError):
    pass


class NinAlreadyVerified(NinError):
    pass


class NinVerificationUnavailable(NinError):
    """The bureau call failed (network/5xx) — a retryable condition."""


@dataclass(frozen=True)
class NinVerifyResult:
    status: str
    # Field NAMES the registry disagreed with, never their values. Surfaced so
    # the route can tell the caller WHICH part did not line up.
    mismatches: tuple[str, ...] = ()


class NinVerificationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        verifier: NinVerifier,
        pepper: str,
        cipher: NinCipher,
    ) -> None:
        self._users = users
        self._verifier = verifier
        self._pepper = pepper
        self._cipher = cipher

    async def verify(
        self,
        *,
        user_id: UUID,
        nin: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> NinVerifyResult:
        # ⚠️ NO ROLE GATE (SCRUM-189). This used to be restricted to sellers
        # with authority_type == "owner", which made NIN unusable as the
        # platform-wide identity check: buyers were hard-403'd, and so was any
        # PoA seller — even though seller onboarding already asked them for a
        # NIN, so that flow was quietly broken for them.
        #
        # The NIN is the national identity number; every role has one and every
        # role needs identity verification. The old gate expressed "only
        # owner-sellers currently NEED this", not "only owner-sellers may
        # safely do this", so widening it removes a restriction rather than a
        # protection. Everything that actually protects the value is unchanged:
        # the caller can only ever verify THEIR OWN id (user_id comes from the
        # JWT, never the body), the value is never returned from this path,
        # `has_nin` still blocks re-submission, and the unique `nin_lookup`
        # still blocks one NIN across two accounts.
        validate_nin_format(nin)  # InvalidNinError -> 422, value never echoed

        if await self._users.has_nin(user_id):
            raise NinAlreadyVerified()

        lookup = lookup_nin(nin, pepper=self._pepper)
        if await self._users.find_user_by_nin_lookup(lookup) is not None:
            # Generic: don't reveal whether it's this user or another account.
            raise NinAlreadyVerified()

        match_first, match_last = await self._resolve_name(
            user_id, first_name=first_name, last_name=last_name
        )

        try:
            outcome = await self._verifier.verify(nin, first_name=match_first, last_name=match_last)
        except NinVerificationError as exc:
            logger.error("nin.verify.provider_unavailable", extra={"user_id": str(user_id)})
            raise NinVerificationUnavailable() from exc

        if outcome.status == "verified":
            await self._users.set_nin_verified(
                user_id,
                nin_hash=hash_nin(nin),
                nin_lookup=lookup,
                nin_encrypted=self._cipher.encrypt(nin, user_id=user_id),
                nin_last4=nin[-4:],
            )
            logger.info("nin.verify.ok", extra={"user_id": str(user_id)})
        else:
            # Nothing is persisted for a `failed` or `pending` outcome, so the
            # caller can correct a typo and try again — and verified_status is
            # left where it was rather than advancing to id_verified.
            logger.info(
                "nin.verify.not_verified",
                extra={
                    "user_id": str(user_id),
                    "status": outcome.status,
                    # Field names only; the values are the caller's own PII.
                    "mismatches": list(outcome.mismatches),
                },
            )

        return NinVerifyResult(status=outcome.status, mismatches=outcome.mismatches)

    async def _resolve_name(
        self, user_id: UUID, *, first_name: str | None, last_name: str | None
    ) -> tuple[str | None, str | None]:
        """Pick the name the registry match is scored against.

        The name ALREADY on the account wins, because that is the name the deal
        documents will carry, and registration has collected one for every role
        since SCRUM-197. A request cannot talk the match into scoring against
        something else.

        The request-supplied name is the fallback for accounts that have none:
        a phone+OTP registration that never completed a profile still carries
        the empty string migration 0001 defaults `full_name` to. When both are
        absent the check degrades to existence-only — exactly what it was
        before this ticket, so no caller gets worse off than they started.
        """
        account = await self._users.get_account(user_id)
        if account is not None and account.full_name.strip():
            return split_full_name(account.full_name)
        supplied_first = (first_name or "").strip() or None
        supplied_last = (last_name or "").strip() or None
        return supplied_first, supplied_last
