"""Registration orchestration.

The route handler stays slim — it builds the service, calls one method,
and translates errors to HTTP status codes. All the side effects
(insert user, persist the verification token, dispatch the email, hit the
rate limiter) live here so they can be unit tested with mocked collaborators.

SCRUM-175: account verification is phone OTP over SMS again, now dispatched
via Twilio. This reverses the channel SCRUM-152 chose (an email magic link)
while leaving that machinery intact and live — email_verification.py,
email_token.py, resend_verification.py, POST /auth/verify/email and the
email_verification_tokens table are all untouched; registration simply no
longer mints a link. That is the exact mirror of what SCRUM-152 did to the
OTP path, so the channel can be flipped back without archaeology.

Note the consequence: because `resend_verification` mints a link for any
account still `unverified`, POST /auth/verify/email/resend remains a
reachable second route to verification. That is deliberate — SMS delivery
to Nigerian numbers from a US long code is unreliable (see adapters/twilio.py),
so an email fallback is worth keeping until a NG sender ID is registered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.adapters.twilio import SmsClient, SmsError
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.otp_repo import OtpRepository
from app.repositories.user_repo import UserRepository
from app.services.otp import generate_code, hash_code
from app.services.password import hash_password
from app.services.rate_limit import OtpRateLimiter

logger = logging.getLogger(__name__)


class RegistrationError(RuntimeError):
    """Base class for registration outcomes that should not be 500s."""


class EmailAlreadyRegistered(RegistrationError):
    pass


class PhoneAlreadyRegistered(RegistrationError):
    pass


class VerificationRateLimited(RegistrationError):
    pass


class OtpDispatchFailed(RegistrationError):
    pass


@dataclass(frozen=True)
class RegistrationResult:
    user_id: UUID
    verification_expires_in_seconds: int


class RegistrationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        credentials: AuthCredentialsRepository,
        rate_limiter: OtpRateLimiter,
        sms: SmsClient,
        otp_expire_minutes: int,
    ) -> None:
        self._users = users
        self._otps = otps
        self._credentials = credentials
        self._rate_limiter = rate_limiter
        self._sms = sms
        self._otp_expire_minutes = otp_expire_minutes

    async def register(
        self,
        *,
        phone: str,
        role: str,
        email: str,
        password: str | None,
        seller_authority_type: str | None,
        full_name: str | None = None,
    ) -> RegistrationResult:
        # Email is still collected and still unique-checked — it is the login
        # identifier (SCRUM-45) even though it is no longer the verification
        # channel, so a duplicate must fail here rather than at the DB.
        if await self._users.get_active_by_email(email) is not None:
            raise EmailAlreadyRegistered()
        if await self._users.get_by_phone(phone) is not None:
            raise PhoneAlreadyRegistered()

        # Rate-limit OTP sends per PHONE (CLAUDE.md §4: 5/hour) — the limiter
        # was keyed on email while the magic link was the channel. Fails open
        # on a Redis outage by design (review.md R5).
        limit = await self._rate_limiter.check_and_record(phone)
        if not limit.allowed:
            raise VerificationRateLimited()

        code = generate_code()
        code_hash = hash_code(code)
        expires_at = datetime.now(UTC) + timedelta(minutes=self._otp_expire_minutes)

        user_id = await self._users.create_with_pii(
            phone=phone,
            role=role,
            email=email,
            seller_authority_type=seller_authority_type,
            full_name=full_name or "",
        )
        # Store the password hash if one was supplied, so the user can later
        # log in via email/password (SCRUM-45).
        if password is not None:
            await self._credentials.upsert(user_id=user_id, password_hash=hash_password(password))
        # Only the bcrypt hash is persisted; the plaintext code exists solely
        # in the SMS body below and is never logged or returned.
        await self._otps.create(
            phone=phone,
            code_hash=code_hash,
            purpose="registration",
            expires_at=expires_at,
        )

        try:
            await self._sms.send_sms(
                phone=phone,
                message=(
                    f"Your Maiplot verification code is {code}. "
                    f"It expires in {self._otp_expire_minutes} minutes."
                ),
            )
        except SmsError as exc:
            # The surrounding request session rolls back on this exception (see
            # db.get_session), so the half-registered user + OTP row are undone
            # and the client can safely retry.
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
            verification_expires_in_seconds=self._otp_expire_minutes * 60,
        )
