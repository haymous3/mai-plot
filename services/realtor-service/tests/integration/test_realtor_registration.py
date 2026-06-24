"""Integration tests for realtor registration (SCRUM-71)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_PDF = b"%PDF-1.4 realtor government id"


def _form() -> dict[str, object]:
    return {
        "esvarbon_number": "esv/1234",
        "years_of_experience": "5",
        "coverage_states": ["Lagos"],
        "coverage_lgas": ["Ikeja"],
    }


def _file() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("id.pdf", _PDF, "application/pdf")}


async def test_register_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.post("/realtors", data=_form(), files=_file())
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
        "/realtors", data=_form(), files=_file(), headers=auth_header(mint_token(user_id, "buyer"))
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

    resp = await http_client.post("/realtors", data=_form(), files=_file(), headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["approval_status"] == "pending"
    assert body["esvarbon_number"] == "ESV/1234"  # normalised
    assert body["coverage_states"] == ["Lagos"]

    me = await http_client.get("/realtors/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["approval_status"] == "pending"


async def test_invalid_esvarbon_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="realtor")
    form = _form() | {"esvarbon_number": "!!"}
    resp = await http_client.post(
        "/realtors", data=form, files=_file(), headers=auth_header(mint_token(user_id, "realtor"))
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "ESVARBON_INVALID"


async def test_bad_id_document_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="realtor")
    bad = {"file": ("id.gif", b"GIF89a nope", "image/gif")}
    resp = await http_client.post(
        "/realtors", data=_form(), files=bad, headers=auth_header(mint_token(user_id, "realtor"))
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "ID_DOCUMENT_INVALID"


async def test_double_register_is_409(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="realtor")
    headers = auth_header(mint_token(user_id, "realtor"))
    first = await http_client.post("/realtors", data=_form(), files=_file(), headers=headers)
    assert first.status_code == 201
    second = await http_client.post("/realtors", data=_form(), files=_file(), headers=headers)
    assert second.status_code == 409
    assert second.json()["error_code"] == "REALTOR_ALREADY_REGISTERED"
