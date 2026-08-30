"""SCRUM-193 — the account holder's own location on POST /auth/profile.

`user_pii.location` answers "where I am", for every role. It is deliberately a
different column from `buyer_profiles.preferred_location` ("where I want to
buy"); migration 0013 explains why they must not be merged.

The tri-state matters and is what most of this file pins down: omitting the
field leaves a stored location alone, while sending an explicit null clears it.
Without that distinction a location could be set but never removed.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import register_and_verify


async def _seller_token(
    http_client: AsyncClient, sms: InMemoryTwilioClient, *, phone: str = "08012345678"
) -> str:
    body = await register_and_verify(
        http_client,
        sms,
        phone=phone,
        role="seller",
        email=f"seller{phone[-4:]}@maihomme.com",
    )
    token: str = body["access_token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _location_of(http_client: AsyncClient, token: str) -> str | None:
    resp = await http_client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    value: str | None = resp.json()["location"]
    return value


@pytest.mark.asyncio
async def test_a_seller_can_set_a_location(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The gap this ticket exists to close: before 0013 a seller had nowhere to
    put one, because the only location column lived on buyer_profiles."""
    token = await _seller_token(http_client, sms_fake)
    assert await _location_of(http_client, token) is None

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "Lagos, Nigeria"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert await _location_of(http_client, token) == "Lagos, Nigeria"


@pytest.mark.asyncio
async def test_omitting_location_leaves_a_stored_one_alone(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """A caller editing only their name must not silently wipe their location.

    This is why the field is tri-state rather than following the `email`
    convention, which cannot express "clear it".
    """
    token = await _seller_token(http_client, sms_fake)
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "Abuja"},
        headers=_auth(token),
    )

    resp = await http_client.post(
        "/auth/profile", json={"full_name": "Ada N. Obi"}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text
    assert await _location_of(http_client, token) == "Abuja"


@pytest.mark.asyncio
async def test_explicit_null_clears_the_location(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    token = await _seller_token(http_client, sms_fake)
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "Abuja"},
        headers=_auth(token),
    )

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": None},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert await _location_of(http_client, token) is None


@pytest.mark.asyncio
async def test_a_blank_location_is_stored_as_absent_not_as_an_empty_string(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """ "Not said" and "said nothing" must read the same way to every consumer."""
    token = await _seller_token(http_client, sms_fake)
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "Abuja"},
        headers=_auth(token),
    )

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "   "},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert await _location_of(http_client, token) is None


@pytest.mark.asyncio
async def test_location_is_independent_of_a_buyers_preferred_location(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The two columns answer different questions and must not bleed together.

    A buyer can be based in Abuja while shopping in Lagos; if writing one moved
    the other, one of those answers would be unrecoverable.
    """
    body = await register_and_verify(
        http_client, sms_fake, phone="08011112222", role="buyer", email="buyer@maihomme.com"
    )
    token: str = body["access_token"]

    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "Abuja"},
        headers=_auth(token),
    )
    await http_client.post(
        "/auth/buyer/profile",
        json={"preferred_location": "Lagos"},
        headers=_auth(token),
    )

    me = await http_client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200, me.text
    assert me.json()["location"] == "Abuja"
    assert me.json()["preferred_location"] == "Lagos"


@pytest.mark.asyncio
async def test_location_is_rejected_when_too_long(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """120 chars, matching the column — a 422 beats a truncated write or a 500."""
    token = await _seller_token(http_client, sms_fake)

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "x" * 121},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# SCRUM-201 — the postal address, collected in onboarding for every role
# --------------------------------------------------------------------------


async def _address_of(http_client: AsyncClient, token: str) -> str | None:
    resp = await http_client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    value: str | None = resp.json()["address"]
    return value


@pytest.mark.asyncio
async def test_a_seller_can_set_an_address(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    token = await _seller_token(http_client, sms_fake)
    assert await _address_of(http_client, token) is None

    resp = await http_client.post(
        "/auth/profile",
        json={
            "full_name": "Ada Obi",
            "address": "12 Admiralty Way, Lekki Phase 1, Lagos",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert await _address_of(http_client, token) == "12 Admiralty Way, Lekki Phase 1, Lagos"


@pytest.mark.asyncio
async def test_address_and_location_are_independent(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """Three place-ish fields now exist and none may bleed into another.

    address = where I live · location = where I am · preferred_location = where
    a buyer wants to buy. Writing one must not disturb the others.
    """
    token = await _seller_token(http_client, sms_fake)

    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "address": "12 Admiralty Way", "location": "Lagos"},
        headers=_auth(token),
    )
    assert await _address_of(http_client, token) == "12 Admiralty Way"
    assert await _location_of(http_client, token) == "Lagos"

    # Change only the location; the address must survive untouched.
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "location": "Abuja"},
        headers=_auth(token),
    )
    assert await _address_of(http_client, token) == "12 Admiralty Way"
    assert await _location_of(http_client, token) == "Abuja"


@pytest.mark.asyncio
async def test_omitting_address_leaves_a_stored_one_alone(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    token = await _seller_token(http_client, sms_fake)
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "address": "12 Admiralty Way"},
        headers=_auth(token),
    )

    resp = await http_client.post(
        "/auth/profile", json={"full_name": "Ada N. Obi"}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text
    assert await _address_of(http_client, token) == "12 Admiralty Way"


@pytest.mark.asyncio
async def test_explicit_null_clears_the_address(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    token = await _seller_token(http_client, sms_fake)
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "address": "12 Admiralty Way"},
        headers=_auth(token),
    )

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "address": None},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert await _address_of(http_client, token) is None


@pytest.mark.asyncio
async def test_a_long_nigerian_address_is_accepted(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """TEXT, not VARCHAR(120) like `location` — an address with an estate name
    and landmark directions runs well past a city name."""
    token = await _seller_token(http_client, sms_fake)
    long_address = (
        "Flat 4B, Block C, Prime Water View Gardens Phase 2, "
        "off Freedom Way, opposite the Lekki Phase 1 roundabout, Lekki, Lagos State"
    )

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "address": long_address},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert await _address_of(http_client, token) == long_address
