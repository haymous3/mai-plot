"""Integration tests for payout-account management (SCRUM-145, SCRUM-223).

paystack_enabled is false in tests, so the fake recipient client mints a
synthetic recipient_code and resolves every account to FAKE_ACCOUNT_NAME —
except numbers ending 0000, which the fake treats as unknown to the bank.

Since SCRUM-223 a PUT needs an `X-Reauth-Token` for the caller — minted here the
way auth-service's POST /auth/reauth mints it (same secret, `type: reauth`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.paystack_recipient import FAKE_ACCOUNT_NAME
from app.config import get_settings

pytestmark = pytest.mark.asyncio

_VALID = {"account_number": "0123456789", "bank_code": "058"}


def _reauth(user_id: UUID, **overrides: Any) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "type": "reauth",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        **overrides,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _headers(
    auth_header: Callable[[str], dict[str, str]], access: str, reauth: str | None
) -> dict[str, str]:
    headers = auth_header(access)
    if reauth is not None:
        headers["X-Reauth-Token"] = reauth
    return headers


async def test_set_then_get_payout_account(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    headers = _headers(auth_header, mint_token(seller, "seller"), _reauth(seller))

    put = await http_client.put("/payout-account", json=_VALID, headers=headers)
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["account_number_masked"] == "••••6789"
    assert body["bank_code"] == "058"
    assert body["account_name"] == FAKE_ACCOUNT_NAME
    assert body["recipient_ready"] is True
    # The full account number is never returned (financial PII).
    assert "0123456789" not in put.text

    get = await http_client.get("/payout-account", headers=headers)
    assert get.status_code == 200, get.text
    assert get.json()["account_number_masked"] == "••••6789"


async def test_a_typed_name_is_ignored_for_the_banks(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """A client from before SCRUM-223 still sends account_name — it must not win."""
    seller = seed_user(role="seller")
    put = await http_client.put(
        "/payout-account",
        json={**_VALID, "account_name": "Somebody Else"},
        headers=_headers(auth_header, mint_token(seller, "seller"), _reauth(seller)),
    )
    assert put.status_code == 200, put.text
    assert put.json()["account_name"] == FAKE_ACCOUNT_NAME


async def test_put_replaces_existing_account_and_audits_both(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    db_engine: Engine,
) -> None:
    seller = seed_user(role="seller")
    headers = _headers(auth_header, mint_token(seller, "seller"), _reauth(seller))

    await http_client.put("/payout-account", json=_VALID, headers=headers)
    updated = {"account_number": "9876543210", "bank_code": "011"}
    put = await http_client.put("/payout-account", json=updated, headers=headers)
    assert put.status_code == 200, put.text
    assert put.json()["account_number_masked"] == "••••3210"

    get = await http_client.get("/payout-account", headers=headers)
    assert get.json()["bank_code"] == "011"

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT old_value, new_value FROM audit_log "
                "WHERE action = 'payout_account.updated' AND actor_id = :u ORDER BY created_at"
            ),
            {"u": seller},
        ).all()
    assert [r.new_value for r in rows] == [
        {"bank_code": "058", "account_last4": "6789"},
        {"bank_code": "011", "account_last4": "3210"},
    ]
    assert rows[1].old_value == {"bank_code": "058", "account_last4": "6789"}
    # Never the full number in the audit trail.
    assert "0123456789" not in repr(rows) and "9876543210" not in repr(rows)


@pytest.mark.parametrize(
    "reauth_for",
    ["missing", "someone_else", "expired", "access_token"],
)
async def test_put_without_a_valid_reauth_for_this_caller_is_403(
    reauth_for: str,
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    db_engine: Engine,
) -> None:
    seller = seed_user(role="seller")
    access = mint_token(seller, "seller")
    reauth = {
        "missing": None,
        # e.g. the same person's buyer account on a shared login (SCRUM-236)
        "someone_else": _reauth(uuid4()),
        "expired": _reauth(seller, exp=int(datetime.now(UTC).timestamp()) - 60),
        "access_token": access,
    }[reauth_for]

    resp = await http_client.put(
        "/payout-account", json=_VALID, headers=_headers(auth_header, access, reauth)
    )

    assert resp.status_code == 403
    assert resp.json()["error_code"] == "REAUTH_REQUIRED"
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM payout_accounts")).scalar_one() == 0


async def test_an_account_the_bank_does_not_know_is_422_and_nothing_is_saved(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    db_engine: Engine,
) -> None:
    seller = seed_user(role="seller")
    resp = await http_client.put(
        "/payout-account",
        json={"account_number": "1234560000", "bank_code": "058"},
        headers=_headers(auth_header, mint_token(seller, "seller"), _reauth(seller)),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "ACCOUNT_NOT_RESOLVED"
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM payout_accounts")).scalar_one() == 0


async def test_resolve_returns_the_banks_name_and_saves_nothing(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    db_engine: Engine,
) -> None:
    seller = seed_user(role="seller")
    headers = auth_header(mint_token(seller, "seller"))

    ok = await http_client.get("/payout-account/resolve", params=_VALID, headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"account_name": FAKE_ACCOUNT_NAME}

    unknown = await http_client.get(
        "/payout-account/resolve",
        params={"account_number": "1234560000", "bank_code": "058"},
        headers=headers,
    )
    assert unknown.status_code == 422
    assert unknown.json()["error_code"] == "ACCOUNT_NOT_RESOLVED"

    bad = await http_client.get(
        "/payout-account/resolve",
        params={"account_number": "12", "bank_code": "058"},
        headers=headers,
    )
    assert bad.status_code == 422

    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM payout_accounts")).scalar_one() == 0


async def test_get_missing_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    resp = await http_client.get(
        "/payout-account", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "PAYOUT_ACCOUNT_NOT_FOUND"


async def test_invalid_account_number_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    resp = await http_client.put(
        "/payout-account",
        json={"account_number": "12", "bank_code": "058"},
        headers=_headers(auth_header, mint_token(realtor, "realtor"), _reauth(realtor)),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


async def test_payout_account_requires_auth(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.get("/payout-account")
    assert resp.status_code == 401
    resolve = await http_client.get("/payout-account/resolve", params=_VALID)
    assert resolve.status_code == 401
