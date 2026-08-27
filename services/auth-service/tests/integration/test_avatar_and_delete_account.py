"""Profile photo + account deletion integration tests (SCRUM-188)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.deals import InMemoryDealChecker
from app.adapters.document_storage import InMemoryDocumentStorage
from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

# Throwaway test value, held in a NON-"password"-named constant and passed by
# reference so secret scanners don't flag a literal in a password-keyed
# position (the convention used across this suite).
_STRONG = "SecurePass123!"

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


async def _account(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    phone: str,
    role: str = "buyer",
) -> tuple[str, str]:
    body = await register_and_verify(
        http_client,
        sms,
        phone=phone,
        role=role,
        email=f"av{phone[-4:]}@maihomme.com",
        password=_STRONG,
    )
    return body["access_token"], body["user"]["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload(data: bytes, name: str = "me.png", content_type: str = "image/png"):  # type: ignore[no-untyped-def]
    return {"file": (name, data, content_type)}


# ── POST /auth/avatar ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_stores_the_image_and_returns_a_url(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    token, user_id = await _account(http_client, sms_fake, phone="08040000001")

    resp = await http_client.post("/auth/avatar", headers=_auth(token), files=_upload(_PNG))

    assert resp.status_code == 200
    url = resp.json()["avatar_url"]
    assert url is not None
    # The object really landed, under a key scoped to this user.
    (key,) = storage_fake.data
    assert key.startswith(f"avatar/{user_id}/")
    assert storage_fake.data[key] == _PNG


@pytest.mark.asyncio
async def test_response_carries_a_url_never_the_s3_key(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    """The bucket is private (§4). Leaking the key tells an attacker exactly
    what to ask for if bucket credentials ever leak too."""
    token, _ = await _account(http_client, sms_fake, phone="08040000002")

    resp = await http_client.post("/auth/avatar", headers=_auth(token), files=_upload(_PNG))

    body = resp.json()
    assert set(body) == {"avatar_url"}


@pytest.mark.asyncio
async def test_a_lying_content_type_is_rejected(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    """The client claims image/png; the bytes are a PDF. Bytes win, and nothing
    is written."""
    token, _ = await _account(http_client, sms_fake, phone="08040000003")

    resp = await http_client.post(
        "/auth/avatar",
        headers=_auth(token),
        files=_upload(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3", name="me.png"),
    )

    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "AVATAR_INVALID")
    assert storage_fake.data == {}


@pytest.mark.asyncio
async def test_replacing_a_photo_deletes_the_previous_object(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    """Every upload mints a fresh uuid key, so without an explicit delete the
    bucket would accumulate one orphan per re-upload."""
    token, _ = await _account(http_client, sms_fake, phone="08040000004")

    await http_client.post("/auth/avatar", headers=_auth(token), files=_upload(_PNG))
    (first_key,) = storage_fake.data

    await http_client.post(
        "/auth/avatar", headers=_auth(token), files=_upload(_JPEG, "me.jpg", "image/jpeg")
    )

    assert first_key not in storage_fake.data
    assert len(storage_fake.data) == 1


@pytest.mark.asyncio
async def test_avatar_url_appears_on_me(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08040000005")

    before = await http_client.get("/auth/me", headers=_auth(token))
    assert before.json()["avatar_url"] is None

    await http_client.post("/auth/avatar", headers=_auth(token), files=_upload(_PNG))

    after = await http_client.get("/auth/me", headers=_auth(token))
    assert after.json()["avatar_url"] is not None


@pytest.mark.asyncio
async def test_upload_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/avatar", files=_upload(_PNG))
    assert resp.status_code in (401, 403)


# ── DELETE /auth/avatar ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_removing_clears_the_object_and_the_pointer(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08040000006")
    await http_client.post("/auth/avatar", headers=_auth(token), files=_upload(_PNG))

    resp = await http_client.delete("/auth/avatar", headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    assert storage_fake.data == {}
    me = await http_client.get("/auth/me", headers=_auth(token))
    assert me.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_removing_when_there_is_no_photo_is_success(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
) -> None:
    """Idempotent — the caller wanted to end up with no photo, and they have."""
    token, _ = await _account(http_client, sms_fake, phone="08040000007")

    resp = await http_client.delete("/auth/avatar", headers=_auth(token))

    assert resp.status_code == 200


# ── POST /auth/account/delete ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_soft_deletes_and_ends_the_session(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
    deals_fake: InMemoryDealChecker,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08040000008")

    resp = await http_client.post("/auth/account/delete", headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json()["sessions_revoked"] is True
    # The account no longer resolves, even with a token that has not expired.
    me = await http_client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 404


@pytest.mark.asyncio
async def test_delete_refuses_while_a_deal_is_in_flight(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
    deals_fake: InMemoryDealChecker,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08040000009")
    deals_fake.has_active = True

    resp = await http_client.post("/auth/account/delete", headers=_auth(token))

    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "ACCOUNT_HAS_ACTIVE_DEALS")
    # Still very much alive.
    me = await http_client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_delete_fails_closed_when_the_guard_is_unreachable(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
    deals_fake: InMemoryDealChecker,
) -> None:
    """503, not 200. "We could not check" must never be treated as "all clear"
    — deleting over an unchecked escrow balance is unrecoverable."""
    token, _ = await _account(http_client, sms_fake, phone="08040000010")
    deals_fake.fail_next = True

    resp = await http_client.post("/auth/account/delete", headers=_auth(token))

    assert resp.status_code == 503
    assert_error_envelope(resp.json(), "DELETE_UNAVAILABLE")
    me = await http_client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_delete_purges_the_profile_photo(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
    deals_fake: InMemoryDealChecker,
) -> None:
    """NDPR erasure: the rows survive for CBN/AMLON, but the face photo goes."""
    token, _ = await _account(http_client, sms_fake, phone="08040000011")
    await http_client.post("/auth/avatar", headers=_auth(token), files=_upload(_PNG))
    assert storage_fake.data != {}

    await http_client.post("/auth/account/delete", headers=_auth(token))

    assert storage_fake.data == {}


@pytest.mark.asyncio
async def test_deleting_twice_reports_gone(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
    deals_fake: InMemoryDealChecker,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08040000012")
    await http_client.post("/auth/account/delete", headers=_auth(token))

    resp = await http_client.post("/auth/account/delete", headers=_auth(token))

    assert resp.status_code in (401, 403, 404)


@pytest.mark.asyncio
async def test_deleted_account_cannot_log_in(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    storage_fake: InMemoryDocumentStorage,
    deals_fake: InMemoryDealChecker,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08040000013")
    await http_client.post("/auth/account/delete", headers=_auth(token))

    resp = await http_client.post(
        "/auth/login",
        json={"email": "av0013@maihomme.com", "password": _STRONG},
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/account/delete")
    assert resp.status_code in (401, 403)
