"""BVN verification orchestration.

Flow (all in-request; the plaintext BVN never leaves this call or reaches
a log, broker, or the database):

1. Validate format (11 digits) -> InvalidBvnError -> 422.
2. Reject if this user already has a BVN, or if the BVN (via its HMAC
   lookup) already belongs to any account -> BvnAlreadyVerified -> 409.
3. Call the bureau adapter with the plaintext BVN.
4. On a verified result, write ONLY the bcrypt hash + HMAC lookup and
   advance verified_status to id_verified.

"BVN hashed with bcrypt before any DB write" holds: the only BVN-derived
values ever written are the bcrypt hash and the HMAC lookup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.bvn import BvnVerificationError, BvnVerifier
from app.repositories.user_repo import UserRepository
from app.services.bvn import hash_bvn, lookup_bvn, validate_bvn_format

logger = logging.getLogger(__name__)


class BvnError(RuntimeError):
    pass


class BvnAlreadyVerified(BvnError):
    pass


class BvnVerificationUnavailable(BvnError):
    """The bureau call failed (network/5xx) — a retryable condition."""


@dataclass(frozen=True)
class BvnVerifyResult:
    status: str


class BvnVerificationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        verifier: BvnVerifier,
        pepper: str,
    ) -> None:
        self._users = users
        self._verifier = verifier
        self._pepper = pepper

    async def verify(self, *, user_id: UUID, bvn: str) -> BvnVerifyResult:
        validate_bvn_format(bvn)  # InvalidBvnError -> 422, value never echoed

        if await self._users.has_bvn(user_id):
            raise BvnAlreadyVerified()

        lookup = lookup_bvn(bvn, pepper=self._pepper)
        if await self._users.find_user_by_bvn_lookup(lookup) is not None:
            # Generic: don't reveal whether it's this user or another account.
            raise BvnAlreadyVerified()

        try:
            outcome = await self._verifier.verify(bvn)
        except BvnVerificationError as exc:
            logger.error("bvn.verify.bureau_unavailable", extra={"user_id": str(user_id)})
            raise BvnVerificationUnavailable() from exc

        if outcome.status == "verified":
            await self._users.set_bvn_verified(user_id, bvn_hash=hash_bvn(bvn), bvn_lookup=lookup)
            logger.info("bvn.verify.ok", extra={"user_id": str(user_id)})
        else:
            logger.info(
                "bvn.verify.not_verified",
                extra={"user_id": str(user_id), "status": outcome.status},
            )

        return BvnVerifyResult(status=outcome.status)
