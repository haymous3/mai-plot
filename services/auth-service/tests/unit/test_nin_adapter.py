"""NinjaNinVerifier response mapping + request shape, against a mock transport.

No network: httpx.MockTransport answers in-process, so these assert the exact
contract we send Ninja and the exact verdict we read back.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.adapters.nin import (
    NinjaNinVerifier,
    NinVerificationError,
    build_nin_verifier,
)

_NIN = "12345678901"


def _verifier(handler: Any) -> NinjaNinVerifier:
    verifier = NinjaNinVerifier(api_url="https://ninja.test", secret_key="sk_test")
    verifier._client = httpx.AsyncClient(
        base_url="https://ninja.test",
        transport=httpx.MockTransport(handler),
    )
    return verifier


@pytest.mark.asyncio
async def test_request_shape_is_ninjas_identify_contract() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"found": True, "recommendation": "accept"})

    await _verifier(handler).verify(_NIN, first_name="Adaeze", last_name="Okonkwo")

    assert seen["url"] == "https://ninja.test/api/identity/identify"
    assert seen["auth"] == "Bearer sk_test"
    assert seen["body"] == {
        "idType": "nin",
        # ⚠️ verify, never lookup — lookup returns the photo, phone and address
        # and none of that may cross af-south-1 (§9) or be stored (§4).
        "mode": "verify",
        "idNumber": _NIN,
        "firstName": "Adaeze",
        "lastName": "Okonkwo",
    }


@pytest.mark.asyncio
async def test_absent_names_are_omitted_not_blanked() -> None:
    """An empty string would score as a mismatch against every real record;
    an absent field is simply not scored."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"found": True, "recommendation": "accept"})

    await _verifier(handler).verify(_NIN, first_name=None, last_name=None)

    assert "firstName" not in seen["body"]
    assert "lastName" not in seen["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("recommendation", "expected"),
    [("accept", "verified"), ("review", "pending"), ("reject", "failed")],
)
async def test_recommendation_maps_to_status(recommendation: str, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"found": True, "verified": True, "recommendation": recommendation}
        )

    outcome = await _verifier(handler).verify(_NIN)
    assert outcome.status == expected


@pytest.mark.asyncio
async def test_recommendation_beats_the_verified_boolean() -> None:
    """`reject` with verified:true must not pass — the recommendation is the
    verdict, the boolean is only the fallback."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"found": True, "verified": True, "recommendation": "reject"}
        )

    assert (await _verifier(handler).verify(_NIN)).status == "failed"


@pytest.mark.asyncio
async def test_not_found_is_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"found": False})

    assert (await _verifier(handler).verify(_NIN)).status == "failed"


@pytest.mark.asyncio
async def test_unknown_recommendation_falls_back_to_the_boolean() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"found": True, "verified": False, "recommendation": "??"})

    assert (await _verifier(handler).verify(_NIN)).status == "failed"


@pytest.mark.asyncio
async def test_mismatched_field_names_are_surfaced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "found": True,
                "recommendation": "review",
                "mismatches": ["last_name"],
                # The values we submitted come back here. They must never
                # escape the adapter — only the field NAMES do.
                "fields": [{"field": "last_name", "provided": "Okonkwo"}],
            },
        )

    outcome = await _verifier(handler).verify(_NIN)
    assert outcome.mismatches == ("last_name",)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 402, 429, 500])
async def test_error_statuses_raise_rather_than_reading_as_unverified(status_code: int) -> None:
    """A provider failure is retryable and must not be mistaken for a clean
    'this NIN is not valid' — 402 (out of credit) especially."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "nope"})

    with pytest.raises(NinVerificationError):
        await _verifier(handler).verify(_NIN)


@pytest.mark.asyncio
async def test_non_json_body_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(NinVerificationError):
        await _verifier(handler).verify(_NIN)


@pytest.mark.asyncio
async def test_transport_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(NinVerificationError):
        await _verifier(handler).verify(_NIN)


def test_factory_picks_the_fake_only_when_asked() -> None:
    fake = build_nin_verifier(use_fake=True, api_url="", secret_key="", timeout_seconds=1.0)
    real = build_nin_verifier(
        use_fake=False, api_url="https://ninja.test", secret_key="sk", timeout_seconds=1.0
    )
    assert type(fake).__name__ == "InMemoryNinVerifier"
    assert isinstance(real, NinjaNinVerifier)
