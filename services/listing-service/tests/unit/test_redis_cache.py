"""get_with_fallback — Redis read with mandatory DB fallback."""

from __future__ import annotations

import pytest
from redis.exceptions import RedisError

from app.adapters.redis_cache import get_with_fallback


class _FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.fail = fail
        self.set_calls = 0

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise RedisError("boom")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls += 1
        self.store[key] = value


@pytest.mark.asyncio
async def test_cache_hit_skips_fallback() -> None:
    redis = _FakeRedis()
    redis.store["k"] = "cached"
    calls = 0

    async def fallback() -> str:
        nonlocal calls
        calls += 1
        return "fresh"

    out = await get_with_fallback(
        redis,  # type: ignore[arg-type]
        "k",
        fallback,
        ttl_seconds=60,
        serialiser=str,
        deserialiser=str,
    )
    assert out == "cached"
    assert calls == 0


@pytest.mark.asyncio
async def test_cache_miss_calls_fallback_and_writes() -> None:
    redis = _FakeRedis()

    async def fallback() -> str:
        return "fresh"

    out = await get_with_fallback(
        redis,  # type: ignore[arg-type]
        "k",
        fallback,
        ttl_seconds=60,
        serialiser=str,
        deserialiser=str,
    )
    assert out == "fresh"
    assert redis.store["k"] == "fresh"
    assert redis.set_calls == 1


@pytest.mark.asyncio
async def test_redis_error_falls_back_to_db() -> None:
    redis = _FakeRedis(fail=True)

    async def fallback() -> str:
        return "fresh"

    # A Redis failure must never crash — fall through to the fallback.
    out = await get_with_fallback(
        redis,  # type: ignore[arg-type]
        "k",
        fallback,
        ttl_seconds=60,
        serialiser=str,
        deserialiser=str,
    )
    assert out == "fresh"


@pytest.mark.asyncio
async def test_none_redis_short_circuits_cache() -> None:
    calls = 0

    async def fallback() -> str:
        nonlocal calls
        calls += 1
        return "fresh"

    out = await get_with_fallback(
        None, "k", fallback, ttl_seconds=60, serialiser=str, deserialiser=str
    )
    assert out == "fresh"
    assert calls == 1
