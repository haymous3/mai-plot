"""Dispatch rate limiter — sliding window, fail-open, per-flow key prefix."""

from __future__ import annotations

import pytest
from redis.exceptions import RedisError

from app.services.rate_limit import OtpRateLimiter


class _FakePipeline:
    def __init__(self, outer: _FakeRedis) -> None:
        self._outer = outer
        self._ops: list[str] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None

    def zremrangebyscore(self, *args: object, **kwargs: object) -> None:
        self._ops.append("zremrangebyscore")
        self._outer.keys_seen.append(str(args[0]))

    def zcard(self, *args: object, **kwargs: object) -> None:
        self._ops.append("zcard")

    async def execute(self) -> list[object]:
        return [None, self._outer.count]


class _FakeRedis:
    def __init__(self, count: int) -> None:
        self.count = count
        self.zadd_calls = 0
        self.keys_seen: list[str] = []

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.zadd_calls += 1
        self.count += 1
        self.keys_seen.append(key)

    async def expire(self, key: str, ttl: int) -> None:
        return None


class _FailingRedis:
    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        raise RedisError("simulated outage")

    async def zadd(self, *_a: object, **_k: object) -> None:  # pragma: no cover
        raise RedisError("simulated outage")

    async def expire(self, *_a: object, **_k: object) -> None:  # pragma: no cover
        raise RedisError("simulated outage")


@pytest.mark.asyncio
async def test_allows_under_limit() -> None:
    fake = _FakeRedis(count=2)
    limiter = OtpRateLimiter(fake, max_per_hour=5)  # type: ignore[arg-type]
    result = await limiter.check_and_record("+2348012345678")
    assert result.allowed is True
    assert result.remaining == 5 - 2 - 1


@pytest.mark.asyncio
async def test_denies_at_limit() -> None:
    fake = _FakeRedis(count=5)
    limiter = OtpRateLimiter(fake, max_per_hour=5)  # type: ignore[arg-type]
    result = await limiter.check_and_record("+2348012345678")
    assert result.allowed is False
    assert result.remaining == 0
    assert fake.zadd_calls == 0  # no record-when-denied


@pytest.mark.asyncio
async def test_fails_open_on_redis_error() -> None:
    limiter = OtpRateLimiter(_FailingRedis(), max_per_hour=5)  # type: ignore[arg-type]
    result = await limiter.check_and_record("+2348012345678")
    assert result.allowed is True  # fail-open per review.md R5
    assert result.remaining == 5


@pytest.mark.asyncio
async def test_passthrough_when_redis_is_none() -> None:
    limiter = OtpRateLimiter(None, max_per_hour=5)
    result = await limiter.check_and_record("+2348012345678")
    assert result.allowed is True
    assert result.remaining == 5


@pytest.mark.asyncio
async def test_default_prefix_is_the_otp_namespace() -> None:
    """Unchanged for existing callers — the OTP flows keep otp:rl:{phone}."""
    fake = _FakeRedis(count=0)
    limiter = OtpRateLimiter(fake, max_per_hour=5)  # type: ignore[arg-type]
    await limiter.check_and_record("+2348012345678")
    assert fake.keys_seen == ["otp:rl:+2348012345678", "otp:rl:+2348012345678"]


@pytest.mark.asyncio
async def test_prefix_separates_two_flows_keyed_on_the_same_email() -> None:
    """The reason the prefix exists (SCRUM-191).

    /auth/verify/email/resend and /auth/password/forgot are both keyed on the
    email. Sharing one namespace would let a password-reset request spend the
    user's verification-resend budget, so the same address must land on two
    distinct Redis keys.
    """
    email = "buyer@example.com"
    resend_redis = _FakeRedis(count=0)
    reset_redis = _FakeRedis(count=0)

    resend = OtpRateLimiter(resend_redis, max_per_hour=5)  # type: ignore[arg-type]
    reset = OtpRateLimiter(reset_redis, max_per_hour=5, key_prefix="pwreset:rl:")  # type: ignore[arg-type]

    await resend.check_and_record(email)
    await reset.check_and_record(email)

    assert resend_redis.keys_seen[0] == f"otp:rl:{email}"
    assert reset_redis.keys_seen[0] == f"pwreset:rl:{email}"
    assert resend_redis.keys_seen[0] != reset_redis.keys_seen[0]
