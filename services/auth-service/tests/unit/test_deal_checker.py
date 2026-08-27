"""Unit tests for HttpDealChecker (SCRUM-188).

Exercises the real httpx path through a mock transport, so the request shape
(URL, forwarded bearer) and — more importantly — every failure branch is
covered. Each branch must raise DealCheckUnavailable rather than returning
False, because False means "this account is clear to delete".
"""

from __future__ import annotations

import httpx
import pytest

from app.adapters.deals import DealCheckUnavailable, HttpDealChecker

pytestmark = pytest.mark.asyncio

_BASE = "http://transaction-service:8000"
_TOKEN = "header.payload.signature"


def _checker() -> HttpDealChecker:
    """A checker pointed at the fake base URL.

    HttpDealChecker builds its own AsyncClient per call, so the mock transport
    is installed by the `patch_transport` fixture rather than injected here.
    """
    return HttpDealChecker(base_url=_BASE)


@pytest.fixture
def patch_transport(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Route every AsyncClient created in the adapter through a mock handler."""

    def _install(handler):  # type: ignore[no-untyped-def]
        original = httpx.AsyncClient.__init__

        def patched(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["transport"] = httpx.MockTransport(handler)
            original(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    return _install


async def test_reports_active_deals(patch_transport) -> None:  # type: ignore[no-untyped-def]
    patch_transport(
        lambda request: httpx.Response(200, json={"active_count": 2, "has_active": True})
    )
    assert await _checker().has_active_deals(bearer_token=_TOKEN) is True


async def test_reports_no_active_deals(patch_transport) -> None:  # type: ignore[no-untyped-def]
    patch_transport(
        lambda request: httpx.Response(200, json={"active_count": 0, "has_active": False})
    )
    assert await _checker().has_active_deals(bearer_token=_TOKEN) is False


async def test_forwards_the_callers_bearer_token(patch_transport) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"active_count": 0, "has_active": False})

    patch_transport(handler)
    await _checker().has_active_deals(bearer_token=_TOKEN)

    assert seen["auth"] == f"Bearer {_TOKEN}"
    assert seen["url"] == f"{_BASE}/transactions/active-deals"


async def test_connection_error_fails_closed(patch_transport) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    patch_transport(handler)
    with pytest.raises(DealCheckUnavailable):
        await _checker().has_active_deals(bearer_token=_TOKEN)


async def test_timeout_fails_closed(patch_transport) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    patch_transport(handler)
    with pytest.raises(DealCheckUnavailable):
        await _checker().has_active_deals(bearer_token=_TOKEN)


@pytest.mark.parametrize("code", [401, 403, 404, 500, 503])
async def test_any_non_200_fails_closed(patch_transport, code: int) -> None:  # type: ignore[no-untyped-def]
    """401/403 included on purpose: if transaction-service will not accept the
    token, we have NOT established that the user is clear."""
    patch_transport(lambda request: httpx.Response(code, json={}))
    with pytest.raises(DealCheckUnavailable):
        await _checker().has_active_deals(bearer_token=_TOKEN)


async def test_unparseable_body_fails_closed(patch_transport) -> None:  # type: ignore[no-untyped-def]
    patch_transport(lambda request: httpx.Response(200, text="not json"))
    with pytest.raises(DealCheckUnavailable):
        await _checker().has_active_deals(bearer_token=_TOKEN)


async def test_missing_key_fails_closed(patch_transport) -> None:  # type: ignore[no-untyped-def]
    """A 200 whose shape we don't recognise is still "unknown", not "clear"."""
    patch_transport(lambda request: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(DealCheckUnavailable):
        await _checker().has_active_deals(bearer_token=_TOKEN)
