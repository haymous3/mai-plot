"""Integration tests for realtor registration (SCRUM-71)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.asyncio


def _form() -> dict[str, object]:
    return {
        "years_of_experience": "5",
        "coverage_states": ["Lagos"],
        "coverage_lgas": ["Ikeja"],
    }


def _stale_file() -> dict[str, tuple[str, bytes, str]]:
    """The credentials document a pre-SCRUM-219 client still posts. Only used by
    the backwards-compatibility test below."""
    return {"file": ("id.pdf", b"%PDF-1.4 realtor government id", "application/pdf")}


async def test_register_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.post("/realtors", data=_form())
    assert resp.status_code == 401


async def test_non_realtor_is_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    resp = await http_client.post(
        "/realtors", data=_form(), headers=auth_header(mint_token(user_id, "buyer"))
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "REALTOR_ROLE_REQUIRED"


async def test_register_happy_then_me(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="realtor")
    headers = auth_header(mint_token(user_id, "realtor"))

    resp = await http_client.post("/realtors", data=_form(), headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["approval_status"] == "pending"
    # No longer collected (SCRUM-207) — the realtor is verified by admin review
    # and issued a Maihomme registration number instead.
    assert body["esvarbon_number"] is None
    assert body["coverage_states"] == ["Lagos"]

    me = await http_client.get("/realtors/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["approval_status"] == "pending"


async def test_esvarbon_is_ignored_if_a_client_still_sends_it(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """SCRUM-207 replaced the 422-on-a-bad-licence test.

    An older client (or a cached bundle mid-deploy) may still post the field.
    That must not 422 and must not be stored: the value is no longer part of the
    contract, and accepting whatever a stale form sends would quietly re-open a
    field the product removed."""
    user_id = seed_user(role="realtor")
    form = _form() | {"esvarbon_number": "!!"}
    resp = await http_client.post(
        "/realtors", data=form, headers=auth_header(mint_token(user_id, "realtor"))
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["esvarbon_number"] is None


async def test_credentials_file_is_ignored_if_a_client_still_sends_one(
    clean_tables: None,
    db_engine: Engine,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """SCRUM-219 replaced the 422-on-a-bad-ID-document test.

    Same shape as the ESVARBON case above: a browser holding a cached bundle
    mid-deploy still attaches the credentials document. That must not 422 — the
    file is simply not part of the contract any more — and no key may be stored
    for it. This is also the one registration test that posts as REAL multipart,
    which is what the frontend sends; the others go up urlencoded, and FastAPI's
    Form() reads either."""
    user_id = seed_user(role="realtor")
    resp = await http_client.post(
        "/realtors",
        data=_form(),
        files=_stale_file(),
        headers=auth_header(mint_token(user_id, "realtor")),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["approval_status"] == "pending"
    with db_engine.begin() as conn:
        key = conn.execute(
            text("SELECT government_id_s3_key FROM realtors WHERE id = :id"),
            {"id": user_id},
        ).scalar_one()
    assert key is None


async def test_double_register_is_409(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="realtor")
    headers = auth_header(mint_token(user_id, "realtor"))
    first = await http_client.post("/realtors", data=_form(), headers=headers)
    assert first.status_code == 201
    second = await http_client.post("/realtors", data=_form(), headers=headers)
    assert second.status_code == 409
    assert second.json()["error_code"] == "REALTOR_ALREADY_REGISTERED"
