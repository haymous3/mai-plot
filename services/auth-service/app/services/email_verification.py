"""Email magic-link verification + JWT issuance (SCRUM-152).

The email counterpart of OtpVerificationService. Single-use enforcement:
the token's used_at is stamped as soon as the hash matches and has not
expired, before tokens are issued. If issuance fails downstream the link is
already burnt — the user requests a fresh email. Same trade-off as the OTP
path (better to re-send than to allow a link twice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.repositories.email_verification_repo import EmailVerificationRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.email_token import hash_token
from app.services.jwt_service import JwtService, TokenPair

logger = logging.getLogger(__name__)


class EmailVerificationError(RuntimeError):
    pass


class EmailTokenInvalid(EmailVerificationError):
    pass


class EmailTokenExpired(EmailVerificationError):
    pass


@dataclass(frozen=True)
class EmailVerificationResult:
    user_id: UUID
    role: str
    verified_status: str
    tokens: TokenPair


class EmailVerificationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: EmailVerificationRepository,
        refresh_tokens: RefreshTokenRepository,
        jwt: JwtService,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._refresh_tokens = refresh_tokens
        self._jwt = jwt

    async def verify(self, *, token: str, purpose: str) -> EmailVerificationResult:
        record = await self._tokens.get_active_by_hash(
            token_hash=hash_token(token), purpose=purpose
        )
        if record is None:
            raise EmailTokenInvalid()

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise EmailTokenExpired()

        user = await self._users.get_active_by_id(record.user_id)
        if user is None:
            # The token points at a user that is gone / deactivated between
            # register and verify. Treat as invalid rather than 500.
            raise EmailTokenInvalid()

        await self._tokens.mark_used(record.id)
        await self._users.mark_email_verified(user.id)

        tokens = self._jwt.issue_pair(user_id=user.id, role=user.role)
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=tokens.refresh_token_hash,
            expires_at=tokens.refresh_expires_at,
        )

        # user.verified_status was read before mark_email_verified, so report
        # the post-update value to the caller.
        verified_status = (
            "email_verified" if user.verified_status == "unverified" else user.verified_status
        )

        logger.info(
            "email_verification.ok",
            extra={"user_id": str(user.id), "role": user.role},
        )
        return EmailVerificationResult(
            user_id=user.id,
            role=user.role,
            verified_status=verified_status,
            tokens=tokens,
        )
