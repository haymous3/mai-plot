"""Forgot-password / reset-password (SCRUM-191).

Both halves of one flow live in this module because they are meaningless
apart: they share the token purpose, and the request half only exists to mint
what the reset half consumes.

The token reuses `email_verification_tokens` — that table is already
purpose-scoped, single-use (`used_at`), expiring, and stores a SHA-256 digest
of a 256-bit value. No migration.

⚠️ The purpose string is deliberately "password_reset", which is NOT a member
of the EmailVerifyPurpose Literal that /auth/verify/email accepts. That route
mints a JWT pair on a valid token, so a reset link must not be redeemable
there — the schema rejects the purpose before the lookup ever runs.

WHO CAN RESET: any active account holding that email, verified or not. It is
tempting to require a verified email first, but /auth/verify/email/resend
already turns an unverified address into a full session, so gating reset on
verification would add friction without closing anything. A user with no email
on file at all cannot use this path — see the SMS blocker in CLAUDE.md §2.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.adapters.email_verification import (
    EmailDeliveryError,
    EmailVerificationSender,
    PasswordResetEmail,
)
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.email_verification_repo import EmailVerificationRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.email_token import build_verify_url, generate_token, hash_token
from app.services.password import hash_password, is_strong
from app.services.rate_limit import OtpRateLimiter
from app.services.set_password import WeakPassword

logger = logging.getLogger(__name__)

PASSWORD_RESET_PURPOSE = "password_reset"

# Redis namespace for the forgot-password budget. Distinct from the OTP /
# verification namespace so a user who just asked to resend their verification
# email still has their full reset allowance (see OtpRateLimiter key_prefix).
RESET_RATE_LIMIT_PREFIX = "pwreset:rl:"


class PasswordResetRateLimited(RuntimeError):
    """Too many reset requests for this address inside the window."""


class ResetTokenInvalid(RuntimeError):
    """No unused reset token matches, or the account behind it is gone."""


class ResetTokenExpired(RuntimeError):
    """The token matched but its window has closed."""


def _email_domain(address: str) -> str:
    """Domain part only, for safe logging — never the full address."""
    _, _, domain = address.rpartition("@")
    return domain or "?"


class ForgotPasswordService:
    """Mint + email a reset link. Never reveals whether the address exists."""

    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: EmailVerificationRepository,
        email_sender: EmailVerificationSender,
        rate_limiter: OtpRateLimiter,
        reset_expire_minutes: int,
        reset_base_url: str,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._email_sender = email_sender
        self._rate_limiter = rate_limiter
        self._reset_expire_minutes = reset_expire_minutes
        self._reset_base_url = reset_base_url

    async def request(self, *, email: str) -> None:
        """Send a reset link if the address has an account.

        Raises PasswordResetRateLimited (-> 429). Every other outcome — unknown
        address, or a send failure — returns normally so the route answers with
        one generic 202. Rate limiting runs FIRST, keyed on the email, so an
        address with no account is throttled on exactly the same schedule as a
        real one and the timing carries no signal either.
        """
        limit = await self._rate_limiter.check_and_record(email)
        if not limit.allowed:
            raise PasswordResetRateLimited()

        user = await self._users.get_active_by_email(email)
        if user is None:
            logger.info("password_reset.noop", extra={"email_domain": _email_domain(email)})
            return

        token = generate_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=self._reset_expire_minutes)
        # Supersede any earlier unused reset links so only the newest one works
        # — otherwise every request a user makes leaves another live key to
        # their account sitting in their inbox.
        await self._tokens.invalidate_active(user_id=user.id, purpose=PASSWORD_RESET_PURPOSE)
        await self._tokens.create(
            user_id=user.id,
            email=email,
            token_hash=hash_token(token),
            purpose=PASSWORD_RESET_PURPOSE,
            expires_at=expires_at,
        )

        # build_verify_url only appends ?token=; the base URL is what makes this
        # a reset link rather than a verification one.
        reset_url = build_verify_url(self._reset_base_url, token)
        try:
            await self._email_sender.send_password_reset(
                PasswordResetEmail(to=email, reset_url=reset_url)
            )
        except EmailDeliveryError as exc:
            # Still return normally: a 500 here would confirm the address has
            # an account. The token is committed; the user can request another.
            logger.error(
                "password_reset.email_failed",
                extra={"email_domain": _email_domain(email), "error": str(exc)},
            )
            return

        logger.info("password_reset.sent", extra={"email_domain": _email_domain(email)})


class ResetPasswordService:
    """Consume a reset token and install the new password."""

    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: EmailVerificationRepository,
        credentials: AuthCredentialsRepository,
        refresh_tokens: RefreshTokenRepository,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._credentials = credentials
        self._refresh_tokens = refresh_tokens

    async def reset(self, *, token: str, new_password: str) -> None:
        """Validate the token, set the password, sign the user out everywhere.

        No JWT pair is issued, unlike /auth/verify/email: whoever holds the link
        may be an attacker who got at the mailbox, and handing back a live
        session would let them keep using the account after the real owner reset
        it again. The client sends the user to /login instead.

        The token is burnt before the password is written; all the writes share
        the request's session, so a failure rolls the whole thing back.
        """
        record = await self._tokens.get_active_by_hash(
            token_hash=hash_token(token), purpose=PASSWORD_RESET_PURPOSE
        )
        if record is None:
            raise ResetTokenInvalid()

        expires_at = record.expires_at
        # Postgres hands back an aware datetime; other drivers may not — same
        # guard as EmailVerificationService.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise ResetTokenExpired()

        # Composition is checked only after the token proves out, so this
        # endpoint cannot be used to probe token validity with a junk password.
        if not is_strong(new_password):
            raise WeakPassword()

        user = await self._users.get_active_by_id(record.user_id)
        if user is None:
            # Account deleted or deactivated between request and reset.
            raise ResetTokenInvalid()

        await self._tokens.mark_used(record.id)
        await self._credentials.upsert(user_id=user.id, password_hash=hash_password(new_password))
        # Any session that predates the reset may belong to whoever the user is
        # locking out. Same policy as /auth/change-password.
        await self._refresh_tokens.revoke_all_for_user(user.id)

        logger.info("password_reset.completed", extra={"user_id": str(user.id)})
