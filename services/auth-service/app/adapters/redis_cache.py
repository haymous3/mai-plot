"""Redis access with mandatory DB fallback (CLAUDE.md non-negotiable).

Every Redis read in this service goes through `get_with_fallback`. If
Redis raises — connection refused, timeout, cluster down — the helper
swallows the error, logs it, and calls the fallback function. Redis
failure must never crash a request.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


async def get_with_fallback[T](
    redis: Redis | None,
    key: str,
    fallback_fn: Callable[[], Awaitable[T]],
    *,
    ttl_seconds: int,
    serialiser: Callable[[T], str] | None = None,
    deserialiser: Callable[[str], T] | None = None,
) -> T:
    """Read from Redis; on miss or error, call fallback and (best-effort) cache.

    `redis` may be None to short-circuit caching entirely — useful in
    tests and in code paths where the value should always be re-derived.
    """
    if redis is not None:
        raw: str | None
        try:
            value_from_redis = await redis.get(key)
        except RedisError as exc:
            logger.warning("redis.read.failed", extra={"key": key, "error": str(exc)})
            raw = None
        else:
            raw = (
                value_from_redis.decode("utf-8")
                if isinstance(value_from_redis, bytes)
                else value_from_redis
            )
        if raw is not None and deserialiser is not None:
            try:
                return deserialiser(raw)
            except (ValueError, TypeError) as exc:
                logger.warning("redis.deserialise.failed", extra={"key": key, "error": str(exc)})

    value = await fallback_fn()

    if redis is not None and serialiser is not None:
        try:
            await redis.set(key, serialiser(value), ex=ttl_seconds)
        except RedisError as exc:
            logger.warning("redis.write.failed", extra={"key": key, "error": str(exc)})

    return value
