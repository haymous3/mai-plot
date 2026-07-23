"""Resend the account-verification email (SCRUM-154).

A user whose magic link expired (or who lost the email) can request a fresh
one from the /verify-email page. The endpoint is public (they aren't verified
or logged in yet) and MUST NOT reveal whether an address has an account — so
the route always returns the same generic 202 and this service treats unknown
/ already-verified addresses as silent no-ops.

Rate limiting happens first, keyed on the email, so unknown addresses are
throttled exactly like real ones (no timing/enumeration signal). Reuses the
same token-mint + send building blocks as registration.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.adapters.email_verification import (
    EmailDeliveryError,
    EmailVerificationSender,
    VerificationEmail,
)
from app.repositories.email_verification_repo import EmailVerificationRepository
from app.repositories.user_repo import UserRepository
from app.services.email_token import build_verify_url, generate_token, hash_token
from app.services.rate_limit import OtpRateLimiter
from app.services.registration import VerificationRateLimited

logger = logging.getLogger(__name__)

_PURPOSE = "registration"


def _email_domain(address: str) -> str:
    """Domain part only, for safe logging — never the full address."""
    _, _, domain = address.rpartition("@")
    return domain or "?"


class ResendVerificationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: EmailVerificationRepository,
        email_sender: EmailVerificationSender,
        rate_limiter: OtpRateLimiter,
        verification_expire_minutes: int,
        verify_base_url: str,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._email_sender = email_sender
        self._rate_limiter = rate_limiter
        self._verification_expire_minutes = verification_expire_minutes
        self._verify_base_url = verify_base_url

    async def resend(self, *, email: str) -> None:
        """Mint + send a fresh verification link for an unverified account.

        Raises VerificationRateLimited (-> 429). Every other outcome — unknown
        address, already-verified account, even a send failure — returns
        normally so the route can answer with one generic 202 (no enumeration).
        """
        limit = await self._rate_limiter.check_and_record(email)
        if not limit.allowed:
            raise VerificationRateLimited()

        user = await self._users.get_active_by_email(email)
        if user is None or user.verified_status != "unverified":
            # No account, or nothing to verify — say nothing different.
            logger.info("resend.noop", extra={"email_domain": _email_domain(email)})
            return

        token = generate_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=self._verification_expire_minutes)
        # Supersede any earlier unused links so only the newest one works.
        await self._tokens.invalidate_active(user_id=user.id, purpose=_PURPOSE)
        await self._tokens.create(
            user_id=user.id,
            email=email,
            token_hash=hash_token(token),
            purpose=_PURPOSE,
            expires_at=expires_at,
        )

        verify_url = build_verify_url(self._verify_base_url, token)
        try:
            await self._email_sender.send_verification(
                VerificationEmail(to=email, verify_url=verify_url)
            )
        except EmailDeliveryError as exc:
            # A send failure must not leak that this address exists + is
            # unverified, so we still return normally (generic 202). The new
            # token is committed; the user can retry. Logged loudly for ops.
            logger.error(
                "resend.email_failed",
                extra={"email_domain": _email_domain(email), "error": str(exc)},
            )
            return

        logger.info("resend.sent", extra={"email_domain": _email_domain(email)})
