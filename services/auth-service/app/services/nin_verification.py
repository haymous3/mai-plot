"""NIN verification orchestration.

Like BVN verification, but gated: per SCRUM-47 only a seller whose
authority_type is `owner` may verify a NIN (PoA sellers go through the PoA
document flow; buyers/realtors use BVN). Eligibility is checked from the
DB because the JWT carries role but not seller_authority_type.

The plaintext NIN never leaves this call or reaches a log, broker, or the
database — only the bcrypt hash and the HMAC lookup are persisted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.nin import NinVerificationError, NinVerifier
from app.repositories.user_repo import UserRepository
from app.services.nin import hash_nin, lookup_nin, validate_nin_format

logger = logging.getLogger(__name__)


class NinError(RuntimeError):
    pass


class NinNotEligible(NinError):
    """Caller is not a seller with authority_type=owner."""


class NinAlreadyVerified(NinError):
    pass


class NinVerificationUnavailable(NinError):
    """The bureau call failed (network/5xx) — a retryable condition."""


@dataclass(frozen=True)
class NinVerifyResult:
    status: str


class NinVerificationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        verifier: NinVerifier,
        pepper: str,
    ) -> None:
        self._users = users
        self._verifier = verifier
        self._pepper = pepper

    async def verify(self, *, user_id: UUID, nin: str) -> NinVerifyResult:
        # Eligibility first: ineligible callers get 403 regardless of payload,
        # and we never process their NIN at all.
        authority = await self._users.get_authority(user_id)
        if (
            authority is None
            or authority.role != "seller"
            or authority.seller_authority_type != "owner"
        ):
            raise NinNotEligible()

        validate_nin_format(nin)  # InvalidNinError -> 422, value never echoed

        if await self._users.has_nin(user_id):
            raise NinAlreadyVerified()

        lookup = lookup_nin(nin, pepper=self._pepper)
        if await self._users.find_user_by_nin_lookup(lookup) is not None:
            # Generic: don't reveal whether it's this user or another account.
            raise NinAlreadyVerified()

        try:
            outcome = await self._verifier.verify(nin)
        except NinVerificationError as exc:
            logger.error("nin.verify.bureau_unavailable", extra={"user_id": str(user_id)})
            raise NinVerificationUnavailable() from exc

        if outcome.status == "verified":
            await self._users.set_nin_verified(user_id, nin_hash=hash_nin(nin), nin_lookup=lookup)
            logger.info("nin.verify.ok", extra={"user_id": str(user_id)})
        else:
            logger.info(
                "nin.verify.not_verified",
                extra={"user_id": str(user_id), "status": outcome.status},
            )

        return NinVerifyResult(status=outcome.status)
