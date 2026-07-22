"""Registration orchestration.

The route handler stays slim — it builds the service, calls one method,
and translates errors to HTTP status codes. All the side effects
(insert user, persist the verification token, dispatch the email, hit the
rate limiter) live here so they can be unit tested with mocked collaborators.

SCRUM-152: account verification moved from phone-OTP-over-SMS to an email
magic link. The OTP machinery (otp.py, otp_repo, otp_verification, the
/auth/otp/verify endpoint, the otp_codes table) is deliberately left intact
and live — registration simply no longer emits an OTP. The old OTP dispatch
is kept as a commented block at the end of `register()` so the delivery
channel can be reverted without archaeology.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.adapters.email_verification import (
    EmailDeliveryError,
    EmailVerificationSender,
    VerificationEmail,
)
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.email_verification_repo import EmailVerificationRepository
from app.repositories.user_repo import UserRepository
from app.services.email_token import generate_token, hash_token
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


class VerificationEmailFailed(RegistrationError):
    pass


@dataclass(frozen=True)
class RegistrationResult:
    user_id: UUID
    verification_expires_in_seconds: int


def _email_domain(address: str) -> str:
    """Domain part only, for safe logging — never the full address."""
    _, _, domain = address.rpartition("@")
    return domain or "?"


class RegistrationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        email_tokens: EmailVerificationRepository,
        credentials: AuthCredentialsRepository,
        rate_limiter: OtpRateLimiter,
        email_sender: EmailVerificationSender,
        verification_expire_minutes: int,
        verify_base_url: str,
    ) -> None:
        self._users = users
        self._email_tokens = email_tokens
        self._credentials = credentials
        self._rate_limiter = rate_limiter
        self._email_sender = email_sender
        self._verification_expire_minutes = verification_expire_minutes
        self._verify_base_url = verify_base_url

    async def register(
        self,
        *,
        phone: str,
        role: str,
        email: str,
        password: str | None,
        seller_authority_type: str | None,
    ) -> RegistrationResult:
        # Email is the verification channel now, so uniqueness is checked first.
        if await self._users.get_active_by_email(email) is not None:
            raise EmailAlreadyRegistered()
        if await self._users.get_by_phone(phone) is not None:
            raise PhoneAlreadyRegistered()

        # Rate-limit verification-email sends per email address to stop a
        # single address being bombarded with links.
        limit = await self._rate_limiter.check_and_record(email)
        if not limit.allowed:
            raise VerificationRateLimited()

        token = generate_token()
        token_hash = hash_token(token)
        expires_at = datetime.now(UTC) + timedelta(minutes=self._verification_expire_minutes)

        user_id = await self._users.create_with_pii(
            phone=phone,
            role=role,
            email=email,
            seller_authority_type=seller_authority_type,
        )
        # Store the password hash if one was supplied, so the user can later
        # log in via email/password (SCRUM-45).
        if password is not None:
            await self._credentials.upsert(user_id=user_id, password_hash=hash_password(password))
        await self._email_tokens.create(
            user_id=user_id,
            email=email,
            token_hash=token_hash,
            purpose="registration",
            expires_at=expires_at,
        )

        verify_url = self._build_verify_url(token)
        try:
            await self._email_sender.send_verification(
                VerificationEmail(to=email, verify_url=verify_url)
            )
        except EmailDeliveryError as exc:
            # The surrounding request session rolls back on this exception (see
            # db.get_session), so the half-registered user + token are undone
            # and the client can safely retry.
            logger.error(
                "registration.verification_email_failed",
                extra={"email_domain": _email_domain(email), "error": str(exc)},
            )
            raise VerificationEmailFailed() from exc

        logger.info(
            "registration.ok",
            extra={
                "user_id": str(user_id),
                "role": role,
                "email_domain": _email_domain(email),
            },
        )
        return RegistrationResult(
            user_id=user_id,
            verification_expires_in_seconds=self._verification_expire_minutes * 60,
        )

        # --- Retained OTP dispatch (SCRUM-152 rollback reference) -------------
        # The phone-OTP flow this replaced. The OTP verify path is still live
        # (POST /auth/otp/verify); only this send was swapped for the email
        # link. To revert the channel, restore the otps/termii collaborators on
        # __init__ and re-enable the block below.
        #
        # from app.adapters.termii import TermiiError
        # from app.services.otp import generate_code, hash_code
        #
        # code = generate_code()
        # code_hash = hash_code(code)
        # await self._otps.create(
        #     phone=phone, code_hash=code_hash, purpose="registration",
        #     expires_at=expires_at,
        # )
        # try:
        #     await self._termii.send_sms(
        #         phone=phone,
        #         message=(
        #             f"Your Maiplot verification code is {code}. "
        #             f"It expires in {self._otp_expire_minutes} minutes."
        #         ),
        #     )
        # except TermiiError as exc:
        #     raise OtpDispatchFailed() from exc
        # ----------------------------------------------------------------------

    def _build_verify_url(self, token: str) -> str:
        """Compose the magic link the email carries. The frontend landing page
        reads the token from the query string and POSTs it to
        /auth/verify/email (the token stays out of server logs that way)."""
        separator = "&" if "?" in self._verify_base_url else "?"
        return f"{self._verify_base_url}{separator}token={token}"
