"""Unit tests for SharedLoginService — switching and adding roles (SCRUM-236)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.email_verification import InMemoryEmailClient
from app.repositories.refresh_token_repo import StoredRefreshToken
from app.repositories.user_repo import UserAccount, UserCore
from app.services.account_link import RoleAlreadyHeld
from app.services.jwt_service import JwtService
from app.services.shared_login import (
    NinVerificationRequired,
    RoleNotHeld,
    RoleNotSwitchable,
    SharedLoginService,
)

pytestmark = pytest.mark.asyncio

_OWNER_EMAIL = "ada@example.com"


def _account(user_id: UUID, *, role: str = "buyer", nin_verified: bool = True) -> UserAccount:
    return UserAccount(
        id=user_id,
        role=role,
        verified_status="id_verified",
        email=_OWNER_EMAIL,
        phone="+2348012345678",
        full_name="Ada Obi",
        first_name="Ada",
        last_name="Obi",
        seller_authority_type=None,
        poa_verified_status="not_applicable",
        bvn_verified=False,
        nin_verified=nin_verified,
        avatar_s3_key=None,
        location="Lagos",
        address="1 Marina, Lagos Island",
    )


@dataclass
class _Row:
    id: UUID
    role: str
    owner: UUID | None = None  # shares_login_with_user_id
    root: UUID | None = None  # linked_identity_user_id
    nin_verified: bool = True


@dataclass
class _Users:
    """An in-memory users table, enough for the login/identity queries."""

    rows: dict[UUID, _Row] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)

    def add(self, row: _Row) -> _Row:
        self.rows[row.id] = row
        return row

    async def get_account(self, user_id: UUID) -> UserAccount | None:
        row = self.rows.get(user_id)
        if row is None:
            return None
        return _account(row.id, role=row.role, nin_verified=row.nin_verified)

    async def login_owner_id(self, user_id: UUID) -> UUID | None:
        row = self.rows.get(user_id)
        return None if row is None else (row.owner or row.id)

    async def identity_root_id(self, user_id: UUID) -> UUID | None:
        row = self.rows.get(user_id)
        return None if row is None else (row.root or row.id)

    async def login_group(self, owner_id: UUID) -> list[UserCore]:
        return [
            UserCore(id=r.id, role=r.role, verified_status="id_verified")
            for r in self.rows.values()
            if r.id == owner_id or r.owner == owner_id
        ]

    async def roles_held_by_identity(self, root_id: UUID) -> set[str]:
        return {r.role for r in self.rows.values() if r.id == root_id or r.root == root_id}

    async def same_person_user_ids(self, user_id: UUID) -> list[UUID]:
        return [i for i in self.rows if i != user_id]

    async def create_with_pii(self, **kwargs: Any) -> UUID:
        new_id = uuid4()
        self.created.append(kwargs)
        self.add(
            _Row(
                id=new_id,
                role=kwargs["role"],
                owner=kwargs["shares_login_with_user_id"],
                root=kwargs["linked_identity_user_id"],
            )
        )
        return new_id


@dataclass
class _RefreshTokens:
    stored: dict[str, StoredRefreshToken] = field(default_factory=dict)
    created_for: list[UUID] = field(default_factory=list)
    revoked: list[UUID] = field(default_factory=list)

    async def create(self, *, user_id: UUID, token_hash: str, expires_at: datetime) -> UUID:
        self.created_for.append(user_id)
        return uuid4()

    async def get_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        return self.stored.get(token_hash)

    async def revoke(self, token_id: UUID) -> None:
        self.revoked.append(token_id)


@dataclass
class _Audit:
    records: list[dict[str, Any]] = field(default_factory=list)

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _jwt() -> JwtService:
    return JwtService(
        secret="x" * 32, issuer="maiplot-test", access_expire_minutes=15, refresh_expire_days=7
    )


@dataclass
class _Rig:
    service: SharedLoginService
    users: _Users
    tokens: _RefreshTokens
    audit: _Audit
    email: InMemoryEmailClient
    jwt: JwtService


def _rig() -> _Rig:
    users, tokens, audit, email, jwt = (
        _Users(),
        _RefreshTokens(),
        _Audit(),
        InMemoryEmailClient(),
        _jwt(),
    )
    service = SharedLoginService(
        users=users,  # type: ignore[arg-type]
        refresh_tokens=tokens,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        jwt=jwt,
        email_sender=email,
    )
    return _Rig(service, users, tokens, audit, email, jwt)


def _held_refresh(rig: _Rig, user_id: UUID) -> tuple[str, UUID]:
    """A live refresh token for `user_id`, registered in the stub store."""
    raw = rig.jwt.issue_pair(user_id=user_id, role="buyer", linked_user_ids=[]).refresh_token
    token_id = uuid4()
    rig.tokens.stored[rig.jwt.hash_token(raw)] = StoredRefreshToken(
        id=token_id,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        revoked_at=None,
    )
    return raw, token_id


# --- switch -----------------------------------------------------------------


async def test_switch_lands_on_the_other_account_and_retires_the_old_session() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))
    seller = rig.users.add(_Row(id=uuid4(), role="seller", owner=buyer.id, root=buyer.id))
    raw, token_id = _held_refresh(rig, buyer.id)

    result = await rig.service.switch(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=raw
    )

    assert result.user_id == seller.id
    assert result.role == "seller"
    assert rig.jwt.decode(result.tokens.access_token, expected_type="access").user_id == seller.id
    assert rig.tokens.created_for == [seller.id]
    assert rig.tokens.revoked == [token_id]


async def test_switch_works_from_the_sharer_back_to_the_owner() -> None:
    rig = _rig()
    seller = rig.users.add(_Row(id=uuid4(), role="seller"))
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer", owner=seller.id, root=seller.id))

    result = await rig.service.switch(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
    )

    assert result.user_id == seller.id


async def test_switch_to_a_role_not_on_the_login_is_refused() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))
    # Another person's seller account: not on this login, must not be reachable.
    rig.users.add(_Row(id=uuid4(), role="seller"))

    with pytest.raises(RoleNotHeld):
        await rig.service.switch(
            caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
        )
    assert rig.tokens.created_for == []


@pytest.mark.parametrize(("caller_role", "target"), [("realtor", "seller"), ("admin", "buyer")])
async def test_realtors_and_staff_cannot_switch(caller_role: str, target: str) -> None:
    rig = _rig()
    caller = rig.users.add(_Row(id=uuid4(), role=caller_role))

    with pytest.raises(RoleNotSwitchable):
        await rig.service.switch(
            caller_id=caller.id, caller_role=caller_role, target_role=target, refresh_token=None
        )


async def test_switch_never_revokes_someone_elses_refresh_token() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))
    rig.users.add(_Row(id=uuid4(), role="seller", owner=buyer.id, root=buyer.id))
    stranger_raw, _ = _held_refresh(rig, uuid4())

    await rig.service.switch(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=stranger_raw
    )

    assert rig.tokens.revoked == []


# --- add_role ---------------------------------------------------------------


async def test_add_role_creates_a_sharer_copying_the_person_and_moves_the_session() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))
    raw, token_id = _held_refresh(rig, buyer.id)

    result = await rig.service.add_role(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=raw
    )

    [created] = rig.users.created
    assert created["role"] == "seller"
    assert created["shares_login_with_user_id"] == buyer.id
    assert created["linked_identity_user_id"] == buyer.id
    assert created["email"] == _OWNER_EMAIL
    assert (created["first_name"], created["last_name"]) == ("Ada", "Obi")
    assert created["phone"] == "+2348012345678"
    assert created["address"] == "1 Marina, Lagos Island"
    # PoA review is per seller account: the authority is declared in onboarding.
    assert created["seller_authority_type"] is None
    assert created["verified_status"] == "id_verified"
    assert created["verification_channel"] == "email"

    assert result.role == "seller"
    assert rig.tokens.created_for == [result.user_id]
    assert rig.tokens.revoked == [token_id]


async def test_add_role_emails_a_receipt_to_the_login_address() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))

    await rig.service.add_role(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
    )

    [sent] = rig.email.sent_role_added
    assert (sent.to, sent.role) == (_OWNER_EMAIL, "seller")


async def test_add_role_is_audited() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))

    result = await rig.service.add_role(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
    )

    [record] = rig.audit.records
    assert record["action"] == "user.role_added"
    assert record["actor_id"] == buyer.id
    assert record["entity_id"] == result.user_id


async def test_add_role_requires_a_verified_nin_and_creates_nothing_without_one() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer", nin_verified=False))

    with pytest.raises(NinVerificationRequired):
        await rig.service.add_role(
            caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
        )
    assert rig.users.created == []
    assert rig.email.sent_role_added == []


async def test_add_role_refuses_a_role_already_on_the_login() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))
    rig.users.add(_Row(id=uuid4(), role="seller", owner=buyer.id, root=buyer.id))

    with pytest.raises(RoleAlreadyHeld):
        await rig.service.add_role(
            caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
        )
    assert rig.users.created == []


async def test_add_role_refuses_a_role_held_on_a_separate_login_of_the_same_person() -> None:
    """A SCRUM-225 seller hanging off a realtor root keeps its own login (0020
    does not merge it); a second seller account is still never wanted."""
    rig = _rig()
    realtor = rig.users.add(_Row(id=uuid4(), role="realtor"))
    rig.users.add(_Row(id=uuid4(), role="seller", root=realtor.id))
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer", root=realtor.id))

    with pytest.raises(RoleAlreadyHeld):
        await rig.service.add_role(
            caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
        )


async def test_add_role_refuses_the_callers_own_role() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))

    with pytest.raises(RoleAlreadyHeld):
        await rig.service.add_role(
            caller_id=buyer.id, caller_role="buyer", target_role="buyer", refresh_token=None
        )


async def test_realtors_cannot_add_a_role_here() -> None:
    rig = _rig()
    realtor = rig.users.add(_Row(id=uuid4(), role="realtor"))

    with pytest.raises(RoleNotSwitchable):
        await rig.service.add_role(
            caller_id=realtor.id, caller_role="realtor", target_role="seller", refresh_token=None
        )


async def test_a_failed_receipt_does_not_fail_the_add() -> None:
    rig = _rig()
    buyer = rig.users.add(_Row(id=uuid4(), role="buyer"))
    rig.email.fail_next = True

    result = await rig.service.add_role(
        caller_id=buyer.id, caller_role="buyer", target_role="seller", refresh_token=None
    )

    assert result.role == "seller"
    assert rig.email.sent_role_added == []
