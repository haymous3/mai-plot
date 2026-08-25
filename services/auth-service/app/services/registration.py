"""Registration orchestration.

The route handler stays slim — it builds the service, calls one method,
and translates errors to HTTP status codes. All the side effects
(insert user, persist the verification token, dispatch the message, hit the
rate limiter) live here so they can be unit tested with mocked collaborators.

SCRUM-180: the caller CHOOSES the verification channel. Both were already
built — email magic link (SCRUM-152) and phone OTP (SCRUM-175/176) — and each
kept working while the other was the default. This makes the choice explicit
rather than a redeploy, so neither has to be torn out again.

`email` is the default and the only channel the UI currently offers: phone OTP
is code-complete but cannot be DELIVERED to Nigerian numbers from the present
sender (see adapters/twilio.py and ng-sender-id-registration.md), so the
frontend shows it as "coming soon". Nothing here is gated on that — pass
channel="phone" and the OTP path runs exactly as before, which is what makes
re-enabling it a UI change rather than a backend one.

Both channels share the rate limiter, but key it differently: email links are
limited per email address, OTP sends per phone (CLAUDE.md §4 caps OTP at
5/hour/phone). Keying each on the identifier it actually spends is the point —
a shared key would let one channel exhaust the other's budget.
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
from app.adapters.twilio import SmsClient, SmsError
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.email_verification_repo import EmailVerificationRepository
from app.repositories.otp_repo import OtpRepository
from app.repositories.user_repo import UserRepository
from app.services.email_token import build_verify_url, generate_token, hash_token
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


class VerificationEmailFailed(RegistrationError):
    pass


@dataclass(frozen=True)
class RegistrationResult:
    user_id: UUID
    verification_expires_in_seconds: int
    # Echoed back so the client routes to the right verify screen and shows the
    # right TTL, without having to remember what it asked for. The TTLs differ
    # materially — 30 minutes for a link, 5 for a code.
    verification_channel: str


def _email_domain(address: str) -> str:
    """Domain part only, for safe logging — never the full address."""
    _, _, domain = address.rpartition("@")
    return domain or "?"


class RegistrationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        email_tokens: EmailVerificationRepository,
        credentials: AuthCredentialsRepository,
        rate_limiter: OtpRateLimiter,
        sms: SmsClient,
        email_sender: EmailVerificationSender,
        otp_expire_minutes: int,
        email_expire_minutes: int,
        verify_base_url: str,
    ) -> None:
        self._users = users
        self._otps = otps
        self._email_tokens = email_tokens
        self._credentials = credentials
        self._rate_limiter = rate_limiter
        self._sms = sms
        self._email_sender = email_sender
        self._otp_expire_minutes = otp_expire_minutes
        self._email_expire_minutes = email_expire_minutes
        self._verify_base_url = verify_base_url

    async def register(
        self,
        *,
        phone: str,
        role: str,
        email: str,
        password: str | None,
        seller_authority_type: str | None,
        full_name: str | None = None,
        verification_channel: str = "email",
    ) -> RegistrationResult:
        by_email = verification_channel == "email"

        # Both identifiers are unique-checked regardless of channel: email is
        # the login identifier (SCRUM-45) and phone is unique in user_pii, so a
        # duplicate on either must fail here rather than at the DB.
        if await self._users.get_active_by_email(email) is not None:
            raise EmailAlreadyRegistered()
        if await self._users.get_by_phone(phone) is not None:
            raise PhoneAlreadyRegistered()

        # Keyed on whichever identifier this send actually spends, so the two
        # channels cannot exhaust each other's budget. Fails open on a Redis
        # outage by design (review.md R5).
        limit = await self._rate_limiter.check_and_record(email if by_email else phone)
        if not limit.allowed:
            raise VerificationRateLimited()

        expire_minutes = self._email_expire_minutes if by_email else self._otp_expire_minutes
        expires_at = datetime.now(UTC) + timedelta(minutes=expire_minutes)

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

        if by_email:
            await self._send_verification_email(user_id=user_id, email=email, expires_at=expires_at)
        else:
            await self._send_otp(phone=phone, expires_at=expires_at)

        logger.info(
            "registration.ok",
            extra={
                "user_id": str(user_id),
                "role": role,
                "channel": verification_channel,
                # Only ever the non-identifying part of whichever identifier
                # this channel used.
                "email_domain": _email_domain(email) if by_email else None,
                "phone_suffix": None if by_email else phone[-4:],
            },
        )
        return RegistrationResult(
            user_id=user_id,
            verification_expires_in_seconds=expire_minutes * 60,
            verification_channel=verification_channel,
        )

    async def _send_verification_email(
        self, *, user_id: UUID, email: str, expires_at: datetime
    ) -> None:
        """Mint a single-use magic link and send it (SCRUM-152).

        Only the SHA-256 hash is persisted; the raw token exists solely in the
        emailed URL.
        """
        token = generate_token()
        await self._email_tokens.create(
            user_id=user_id,
            email=email,
            token_hash=hash_token(token),
            purpose="registration",
            expires_at=expires_at,
        )
        try:
            verify_url = build_verify_url(self._verify_base_url, token)
            await self._email_sender.send_verification(
                VerificationEmail(to=email, verify_url=verify_url)
            )
        except EmailDeliveryError as exc:
            # Same non-rollback behaviour as the OTP path below — the route
            # catches this to return a 502, so the session still commits and
            # the account persists. Recovery is POST /auth/verify/email/resend.
            logger.error(
                "registration.verification_email_failed",
                extra={"email_domain": _email_domain(email), "error": str(exc)},
            )
            raise VerificationEmailFailed() from exc

    async def _send_otp(self, *, phone: str, expires_at: datetime) -> None:
        """Mint a 6-digit code and text it (SCRUM-175).

        Only the bcrypt hash is persisted; the plaintext exists solely in the
        SMS body and is never logged or returned.
        """
        code = generate_code()
        await self._otps.create(
            phone=phone,
            code_hash=hash_code(code),
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
            # This does NOT roll back: db.get_session only rolls back when an
            # exception escapes the ROUTE, and the route catches this to return
            # a 502 — so the session commits and the user + OTP rows persist.
            # That is what we want, because the caller recovers with
            # POST /auth/otp/resend (SCRUM-176) instead of re-entering the form.
            logger.error(
                "registration.otp_dispatch_failed",
                extra={"phone_suffix": phone[-4:], "error": str(exc)},
            )
            raise OtpDispatchFailed() from exc
