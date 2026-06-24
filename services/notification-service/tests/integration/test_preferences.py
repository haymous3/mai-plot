"""Integration tests for notification preferences + unsubscribe (SCRUM-122)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.services.unsubscribe_token import make_unsubscribe_token

pytestmark = pytest.mark.asyncio


async def test_get_preferences_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/notifications/preferences")
    assert resp.status_code == 401


async def test_defaults_then_patch_round_trips(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user()
    headers = auth_header(mint_token(user_id, "buyer"))

    # Defaults: everything on (no row yet).
    got = await http_client.get("/notifications/preferences", headers=headers)
    assert got.status_code == 200
    assert got.json() == {"push_enabled": True, "sms_enabled": True, "email_enabled": True}

    # Partial update: disable email only.
    patched = await http_client.patch(
        "/notifications/preferences", json={"email_enabled": False}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json() == {"push_enabled": True, "sms_enabled": True, "email_enabled": False}

    # Persisted.
    again = await http_client.get("/notifications/preferences", headers=headers)
    assert again.json()["email_enabled"] is False


async def test_unsubscribe_with_valid_token_disables_email(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user()
    token = make_unsubscribe_token(user_id, secret=get_settings().unsubscribe_secret)

    resp = await http_client.get(
        "/notifications/unsubscribe", params={"uid": str(user_id), "token": token}
    )
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()

    # Email is now off for that user.
    headers = auth_header(mint_token(user_id, "buyer"))
    prefs = await http_client.get("/notifications/preferences", headers=headers)
    assert prefs.json()["email_enabled"] is False


async def test_unsubscribe_with_bad_token_changes_nothing(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user()
    resp = await http_client.get(
        "/notifications/unsubscribe", params={"uid": str(user_id), "token": "forged"}
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_UNSUBSCRIBE_TOKEN"

    headers = auth_header(mint_token(user_id, "buyer"))
    prefs = await http_client.get("/notifications/preferences", headers=headers)
    assert prefs.json()["email_enabled"] is True  # unchanged


async def test_unsubscribe_for_one_user_does_not_affect_another(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
) -> None:
    victim = seed_user()
    # A token minted for a different user must not unsubscribe the victim.
    other_token = make_unsubscribe_token(uuid4(), secret=get_settings().unsubscribe_secret)
    resp = await http_client.get(
        "/notifications/unsubscribe", params={"uid": str(victim), "token": other_token}
    )
    assert resp.status_code == 400
