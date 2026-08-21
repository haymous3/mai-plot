"""Resend a registration OTP (SCRUM-176).

The design for the verify-OTP screen puts a "Resend code" affordance on
every state, and nothing backed it: /auth/register 400s once the phone is
registered, so a user whose SMS never arrived had no way forward except
the email magic link. This is that missing path.

Deliberately mirrors ResendVerificationService (SCRUM-154), because the
enumeration properties are identical and worth keeping identical: only the
rate limit surfaces a distinct status. Unknown number, already-verified
account, even a failed SMS send all return normally so the route can
answer with one generic 202 — a caller must not be able to probe which
Nigerian numbers hold Maiplot accounts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.adapters.twilio import SmsClient, SmsError
from app.repositories.otp_repo import OtpRepository
from app.repositories.user_repo import UserRepository
from app.services.otp import generate_code, hash_code
from app.services.rate_limit import OtpRateLimiter
from app.services.registration import VerificationRateLimited

logger = logging.getLogger(__name__)

_PURPOSE = "registration"


class OtpResendService:
    def __init__(
        self,
        *,
        users: UserRepository,
        otps: OtpRepository,
        sms: SmsClient,
        rate_limiter: OtpRateLimiter,
        otp_expire_minutes: int,
    ) -> None:
        self._users = users
        self._otps = otps
        self._sms = sms
        self._rate_limiter = rate_limiter
        self._otp_expire_minutes = otp_expire_minutes

    async def resend(self, *, phone: str) -> None:
        """Mint + send a fresh code for an unverified account.

        Raises VerificationRateLimited (-> 429). Every other outcome —
        unknown number, already-verified account, even a send failure —
        returns normally so the route can answer with one generic 202.
        """
        # Checked BEFORE the user lookup, so a rate-limited caller learns
        # nothing about whether the number exists.
        limit = await self._rate_limiter.check_and_record(phone)
        if not limit.allowed:
            raise VerificationRateLimited()

        user = await self._users.get_by_phone(phone)
        if user is None or user.verified_status != "unverified":
            # No account, or nothing to verify — say nothing different.
            logger.info("otp_resend.noop", extra={"phone_suffix": phone[-4:]})
            return

        code = generate_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=self._otp_expire_minutes)
        # Supersede any earlier unused codes so only the newest one works —
        # otherwise a resend leaves the previous code live for the rest of its
        # window, and its spent attempt counter with it.
        await self._otps.invalidate_active(phone=phone, purpose=_PURPOSE)
        await self._otps.create(
            phone=phone,
            code_hash=hash_code(code),
            purpose=_PURPOSE,
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
            # A send failure must not leak that this number exists and is
            # unverified, so we still return normally (generic 202). The new
            # code is committed; the user can retry. Logged loudly for ops —
            # and this is the path that fires when Nigerian carriers drop the
            # US long code, so it is worth alerting on.
            logger.error(
                "otp_resend.sms_failed",
                extra={"phone_suffix": phone[-4:], "error": str(exc)},
            )
            return

        logger.info("otp_resend.sent", extra={"phone_suffix": phone[-4:]})
