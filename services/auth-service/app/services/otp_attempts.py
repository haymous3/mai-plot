"""Failed-attempt cap for OTP verification (SCRUM-176).

A 6-digit code is only 1,000,000 possibilities. Without a cap, an attacker
who knows a registered phone number can simply keep POSTing to
/auth/otp/verify until one lands — the 5-minute TTL is the only thing
slowing them down, and it does not slow them much. This caps failures per
CODE, so a burst of wrong guesses burns the code instead of eventually
finding it.

Keyed on the OTP row id, not the phone: a resend mints a new row, which
starts the caller on a fresh allowance. That is the behaviour the UI
promises ("send a new code" is the way out of a lockout) and it means a
resend cannot be used to keep an old code alive.

Fails OPEN on Redis trouble, matching OtpRateLimiter and review.md R5: a
Redis hiccup must not lock legitimate users out of their own signup. The
DB-side single-use and expiry guarantees still hold when this degrades —
this is defence in depth, not the only defence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttemptResult:
    """Outcome of recording one failed verification.

    `exhausted` is True on the attempt that reaches the cap, so the caller
    knows to burn the code. `remaining` is what the UI shows the user.
    """

    exhausted: bool
    remaining: int


class OtpAttemptLimiter:
    def __init__(self, redis: Redis | None, *, max_attempts: int) -> None:
        self._redis = redis
        self._max = max_attempts

    def _key(self, otp_id: UUID) -> str:
        return f"otp:attempts:{otp_id}"

    async def record_failure(self, otp_id: UUID, *, ttl_seconds: int) -> AttemptResult:
        """Count one wrong code. Fails open (never exhausted) on Redis error.

        The key expires with the OTP it guards, so nothing accumulates.
        """
        if self._redis is None:
            return AttemptResult(exhausted=False, remaining=self._max)

        key = self._key(otp_id)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                # Re-stamped every failure rather than set once: NX on a key
                # that INCR just created is a race, and re-stamping is
                # harmless — the ceiling is still the OTP's own lifetime.
                pipe.expire(key, ttl_seconds)
                count, _ = await pipe.execute()
        except RedisError as exc:
            logger.warning(
                "otp_attempts.record.failed",
                extra={"otp_id": str(otp_id), "error": str(exc)},
            )
            return AttemptResult(exhausted=False, remaining=self._max)

        used = int(count)
        remaining = max(self._max - used, 0)
        return AttemptResult(exhausted=used >= self._max, remaining=remaining)

    async def clear(self, otp_id: UUID) -> None:
        """Drop the counter once the code has been used successfully."""
        if self._redis is None:
            return
        try:
            await self._redis.delete(self._key(otp_id))
        except RedisError as exc:
            logger.warning(
                "otp_attempts.clear.failed",
                extra={"otp_id": str(otp_id), "error": str(exc)},
            )
