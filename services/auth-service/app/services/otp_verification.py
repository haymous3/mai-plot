"""OTP verification + JWT issuance.

Single-use enforcement: we mark the OTP `used_at` as soon as the bcrypt
check passes, before issuing tokens. If token issuance fails downstream
the OTP is already burnt — the caller has to request a fresh code. That
is the correct tradeoff (better to ask the user to retry than to allow
the same code twice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.repositories.otp_repo import OtpRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.jwt_service import JwtService, TokenPair
from app.services.otp import verify_code

logger = logging.getLogger(__name__)


class OtpVerificationError(RuntimeError):
    pass


class OtpInvalid(OtpVerificationError):
    pass


class OtpExpired(OtpVerificationError):
    pass


@dataclass(frozen=True)
class VerificationResult:
    user_id: UUID
    role: str
    verified_status: str
    tokens: TokenPair


class OtpVerificationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        refresh_tokens: RefreshTokenRepository,
        jwt: JwtService,
    ) -> None:
        self._users = users
        self._otps = otps
        self._refresh_tokens = refresh_tokens
        self._jwt = jwt

    async def verify(self, *, phone: str, code: str, purpose: str) -> VerificationResult:
        otp = await self._otps.get_active(phone=phone, purpose=purpose)
        if otp is None:
            raise OtpInvalid()

        expires_at = otp.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise OtpExpired()

        if not verify_code(code, otp.code_hash):
            raise OtpInvalid()

        user = await self._users.get_by_phone(phone)
        if user is None:
            # Defensive: an OTP exists for a phone that has no user. This
            # should not happen unless the user row was deleted between
            # register and verify; treat as invalid rather than 500.
            raise OtpInvalid()

        await self._otps.mark_used(otp.id)
        await self._users.mark_phone_verified(user.id)

        tokens = self._jwt.issue_pair(user_id=user.id, role=user.role)
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=tokens.refresh_token_hash,
            expires_at=tokens.refresh_expires_at,
        )

        # The user.verified_status we read above predates mark_phone_verified,
        # so report the post-update value to the caller.
        verified_status = (
            "phone_verified" if user.verified_status == "unverified" else user.verified_status
        )

        logger.info(
            "otp_verification.ok",
            extra={"user_id": str(user.id), "role": user.role, "phone_suffix": phone[-4:]},
        )
        return VerificationResult(
            user_id=user.id,
            role=user.role,
            verified_status=verified_status,
            tokens=tokens,
        )
