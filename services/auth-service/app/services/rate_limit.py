"""Per-phone OTP rate limiter — Redis sliding window with fail-open.

Why fail-open: review.md R5 — if Redis is unavailable, the limiter must
not block legitimate registration traffic. Better to occasionally allow
a 6th OTP in an hour than to wedge every user out when Redis hiccups.
Kong already enforces a per-IP cap (10/min) as a coarse safety net.

The sliding window uses a Redis sorted set keyed by phone, with member
timestamps as scores. `ZREMRANGEBYSCORE` trims old entries before each
`ZCARD`; `ZADD` records the new attempt. One Redis round trip per
register call.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int


class OtpRateLimiter:
    def __init__(self, redis: Redis | None, *, max_per_hour: int) -> None:
        self._redis = redis
        self._max = max_per_hour
        self._window_seconds = 3600

    def _key(self, phone: str) -> str:
        return f"otp:rl:{phone}"

    async def check_and_record(self, phone: str) -> RateLimitResult:
        """Allow or deny one OTP dispatch attempt. Fails open on Redis error."""
        if self._redis is None:
            return RateLimitResult(allowed=True, remaining=self._max)

        now = time.time()
        cutoff = now - self._window_seconds
        key = self._key(phone)

        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zcard(key)
                _, count = await pipe.execute()
        except RedisError as exc:
            logger.warning(
                "rate_limit.read.failed",
                extra={"phone_suffix": phone[-4:], "error": str(exc)},
            )
            return RateLimitResult(allowed=True, remaining=self._max)

        if count >= self._max:
            return RateLimitResult(allowed=False, remaining=0)

        try:
            await self._redis.zadd(key, {f"{now}:{count}": now})
            await self._redis.expire(key, self._window_seconds)
        except RedisError as exc:
            logger.warning(
                "rate_limit.record.failed",
                extra={"phone_suffix": phone[-4:], "error": str(exc)},
            )

        return RateLimitResult(allowed=True, remaining=self._max - count - 1)
