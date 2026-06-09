"""Registration orchestration.

The route handler stays slim — it builds the service, calls one method,
and translates errors to HTTP status codes. All the side effects
(insert user, persist OTP, dispatch SMS, hit the rate limiter) live here
so they can be unit tested with mocked repositories.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.adapters.termii import TermiiClient, TermiiError
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.otp_repo import OtpRepository
from app.repositories.user_repo import UserRepository
from app.services.otp import generate_code, hash_code
from app.services.password import hash_password
from app.services.rate_limit import OtpRateLimiter

logger = logging.getLogger(__name__)


class RegistrationError(RuntimeError):
    """Base class for registration outcomes that should not be 500s."""


class PhoneAlreadyRegistered(RegistrationError):
    pass


class OtpRateLimited(RegistrationError):
    pass


class OtpDispatchFailed(RegistrationError):
    pass


@dataclass(frozen=True)
class RegistrationResult:
    user_id: UUID
    otp_expires_in_seconds: int


class RegistrationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        credentials: AuthCredentialsRepository,
        rate_limiter: OtpRateLimiter,
        termii: TermiiClient,
        otp_expire_minutes: int,
    ) -> None:
        self._users = users
        self._otps = otps
        self._credentials = credentials
        self._rate_limiter = rate_limiter
        self._termii = termii
        self._otp_expire_minutes = otp_expire_minutes

    async def register(
        self,
        *,
        phone: str,
        role: str,
        email: str | None,
        password: str | None,
        seller_authority_type: str | None,
    ) -> RegistrationResult:
        existing = await self._users.get_by_phone(phone)
        if existing is not None:
            raise PhoneAlreadyRegistered()

        limit = await self._rate_limiter.check_and_record(phone)
        if not limit.allowed:
            raise OtpRateLimited()

        code = generate_code()
        code_hash = hash_code(code)
        expires_at = datetime.now(UTC) + timedelta(minutes=self._otp_expire_minutes)

        user_id = await self._users.create_with_pii(
            phone=phone,
            role=role,
            email=email,
            seller_authority_type=seller_authority_type,
        )
        # Store the password hash if one was supplied, so the user can later
        # log in via email/password (SCRUM-45). Phone-OTP-only users skip this.
        if password is not None:
            await self._credentials.upsert(user_id=user_id, password_hash=hash_password(password))
        await self._otps.create(
            phone=phone,
            code_hash=code_hash,
            purpose="registration",
            expires_at=expires_at,
        )

        try:
            await self._termii.send_sms(
                phone=phone,
                message=(
                    f"Your Maiplot verification code is {code}. "
                    f"It expires in {self._otp_expire_minutes} minutes."
                ),
            )
        except TermiiError as exc:
            logger.error(
                "registration.otp_dispatch_failed",
                extra={"phone_suffix": phone[-4:], "error": str(exc)},
            )
            raise OtpDispatchFailed() from exc

        logger.info(
            "registration.ok",
            extra={
                "user_id": str(user_id),
                "role": role,
                "phone_suffix": phone[-4:],
            },
        )
        return RegistrationResult(
            user_id=user_id,
            otp_expires_in_seconds=self._otp_expire_minutes * 60,
        )
