"""OTP rate limiter — sliding window correctness + fail-open behaviour."""

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

    def zcard(self, *args: object, **kwargs: object) -> None:
        self._ops.append("zcard")

    async def execute(self) -> list[object]:
        return [None, self._outer.count]


class _FakeRedis:
    def __init__(self, count: int) -> None:
        self.count = count
        self.zadd_calls = 0

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.zadd_calls += 1
        self.count += 1

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
