"""OTP failed-attempt cap — counting, exhaustion and fail-open (SCRUM-176)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from app.services.otp_attempts import OtpAttemptLimiter


class _FakePipeline:
    def __init__(self, outer: _FakeRedis) -> None:
        self._outer = outer

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None

    def incr(self, key: str) -> None:
        self._outer.counts[key] = self._outer.counts.get(key, 0) + 1
        self._outer.pending = self._outer.counts[key]

    def expire(self, key: str, ttl: int) -> None:
        self._outer.ttls[key] = ttl

    async def execute(self) -> list[object]:
        return [self._outer.pending, True]


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.pending = 0
        self.deleted: list[str] = []

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.counts.pop(key, None)


class _FailingRedis:
    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        raise RedisError("simulated outage")

    async def delete(self, key: str) -> None:
        raise RedisError("simulated outage")


@pytest.mark.asyncio
async def test_counts_down_and_exhausts_on_the_cap() -> None:
    limiter = OtpAttemptLimiter(_FakeRedis(), max_attempts=3)  # type: ignore[arg-type]
    otp_id = uuid4()

    first = await limiter.record_failure(otp_id, ttl_seconds=300)
    assert (first.exhausted, first.remaining) == (False, 2)

    second = await limiter.record_failure(otp_id, ttl_seconds=300)
    assert (second.exhausted, second.remaining) == (False, 1)

    # The third failure reaches the cap — the caller burns the code on this.
    third = await limiter.record_failure(otp_id, ttl_seconds=300)
    assert (third.exhausted, third.remaining) == (True, 0)


@pytest.mark.asyncio
async def test_remaining_never_goes_negative() -> None:
    limiter = OtpAttemptLimiter(_FakeRedis(), max_attempts=1)  # type: ignore[arg-type]
    otp_id = uuid4()
    await limiter.record_failure(otp_id, ttl_seconds=300)
    extra = await limiter.record_failure(otp_id, ttl_seconds=300)
    assert extra.exhausted is True
    assert extra.remaining == 0


@pytest.mark.asyncio
async def test_counters_are_per_otp_not_per_process() -> None:
    """A resend mints a new OTP row, which must start on a fresh allowance."""
    redis = _FakeRedis()
    limiter = OtpAttemptLimiter(redis, max_attempts=3)  # type: ignore[arg-type]
    old_otp, new_otp = uuid4(), uuid4()

    await limiter.record_failure(old_otp, ttl_seconds=300)
    await limiter.record_failure(old_otp, ttl_seconds=300)

    fresh = await limiter.record_failure(new_otp, ttl_seconds=300)
    assert (fresh.exhausted, fresh.remaining) == (False, 2)


@pytest.mark.asyncio
async def test_key_expires_with_the_code() -> None:
    redis = _FakeRedis()
    limiter = OtpAttemptLimiter(redis, max_attempts=3)  # type: ignore[arg-type]
    otp_id = uuid4()
    await limiter.record_failure(otp_id, ttl_seconds=300)
    assert redis.ttls[f"otp:attempts:{otp_id}"] == 300


@pytest.mark.asyncio
async def test_fails_open_when_redis_errors() -> None:
    """review.md R5: a Redis outage must not lock users out of their signup.
    The DB-side single-use and expiry checks still apply."""
    limiter = OtpAttemptLimiter(_FailingRedis(), max_attempts=3)  # type: ignore[arg-type]
    result = await limiter.record_failure(uuid4(), ttl_seconds=300)
    assert result.exhausted is False
    assert result.remaining == 3


@pytest.mark.asyncio
async def test_fails_open_when_redis_absent() -> None:
    limiter = OtpAttemptLimiter(None, max_attempts=3)
    result = await limiter.record_failure(uuid4(), ttl_seconds=300)
    assert result.exhausted is False
    assert result.remaining == 3


@pytest.mark.asyncio
async def test_clear_drops_the_counter() -> None:
    redis = _FakeRedis()
    limiter = OtpAttemptLimiter(redis, max_attempts=3)  # type: ignore[arg-type]
    otp_id = uuid4()
    await limiter.record_failure(otp_id, ttl_seconds=300)
    await limiter.clear(otp_id)
    assert redis.deleted == [f"otp:attempts:{otp_id}"]


@pytest.mark.asyncio
async def test_clear_swallows_redis_errors() -> None:
    limiter = OtpAttemptLimiter(_FailingRedis(), max_attempts=3)  # type: ignore[arg-type]
    await limiter.clear(uuid4())  # must not raise — success already committed
