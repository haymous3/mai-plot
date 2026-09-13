"""AccountLinkService — matching a claimed existing account by NIN (SCRUM-225)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.user_repo import IdentityMatch
from app.services.account_link import AccountLinkService, RoleAlreadyHeld
from app.services.nin import lookup_nin

_PEPPER = "unit-test-nin-pepper"
_NIN = "12345678901"


class _StubUserRepo:
    def __init__(
        self,
        *,
        match: IdentityMatch | None = None,
        roles: set[str] | None = None,
        root_override: UUID | None = None,
    ) -> None:
        self._match = match
        self._roles = roles or set()
        self._root_override = root_override
        self.lookups: list[str] = []

    async def find_identity_by_nin_lookup(self, nin_lookup: str) -> IdentityMatch | None:
        self.lookups.append(nin_lookup)
        return self._match

    async def identity_root_id(self, user_id: UUID) -> UUID | None:
        return self._root_override or user_id

    async def roles_held_by_identity(self, root_user_id: UUID) -> set[str]:
        return self._roles


def _service(repo: _StubUserRepo) -> AccountLinkService:
    return AccountLinkService(users=repo, pepper=_PEPPER)  # type: ignore[arg-type]


def _match(**overrides: object) -> IdentityMatch:
    base = {
        "user_id": uuid4(),
        "email": "root@example.com",
        "role": "seller",
        "full_name": "Adaeze Okonkwo",
        # Pre-0019 shape by default: parts absent, only full_name. Tests that
        # want the stored-parts path override these.
        "first_name": None,
        "last_name": None,
    }
    base.update(overrides)
    return IdentityMatch(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_match_returns_the_roots_email_not_the_new_one() -> None:
    """⚠️ THE security property. The confirmation must be addressed to the
    EXISTING account, so only someone who can open that mailbox completes the
    signup. A NIN is not secret; this is what stops it being a credential."""
    match = _match(email="root@example.com")
    repo = _StubUserRepo(match=match, roles={"seller"})

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="Adaeze", claimed_last_name="Okonkwo", requested_role="realtor"
    )

    assert decision.is_link
    assert decision.root_user_id == match.user_id
    assert decision.notify_email == "root@example.com"


@pytest.mark.asyncio
async def test_the_nin_is_looked_up_by_peppered_hmac_never_in_the_clear() -> None:
    repo = _StubUserRepo(match=_match())
    await _service(repo).decide(
        nin=_NIN, claimed_first_name="Adaeze", claimed_last_name="Okonkwo", requested_role="realtor"
    )

    assert repo.lookups == [lookup_nin(_NIN, pepper=_PEPPER)]
    assert _NIN not in repo.lookups[0]


@pytest.mark.asyncio
async def test_unknown_nin_is_no_match_not_an_error() -> None:
    """A miss must not fail the request — registration carries on as an
    ordinary signup, so a mistyped NIN cannot dead-end the funnel."""
    decision = await _service(_StubUserRepo(match=None)).decide(
        nin=_NIN, claimed_first_name="Adaeze", claimed_last_name="Okonkwo", requested_role="realtor"
    )

    assert not decision.is_link
    assert decision.notify_email is None


@pytest.mark.asyncio
async def test_wrong_name_does_not_match_even_with_the_right_nin() -> None:
    """Knowing the NIN alone must never be enough."""
    repo = _StubUserRepo(match=_match(full_name="Adaeze Okonkwo"))

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="Someone", claimed_last_name="Else", requested_role="realtor"
    )

    assert not decision.is_link


@pytest.mark.asyncio
async def test_name_match_ignores_case_and_middle_names() -> None:
    repo = _StubUserRepo(match=_match(full_name="Adaeze Ngozi Okonkwo"))

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="adaeze", claimed_last_name="okonkwo", requested_role="realtor"
    )

    assert decision.is_link


@pytest.mark.asyncio
async def test_a_root_with_no_name_on_file_can_never_be_matched() -> None:
    """Otherwise an empty stored name would make the NIN sufficient on its own."""
    repo = _StubUserRepo(match=_match(full_name=""))

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="Adaeze", claimed_last_name="Okonkwo", requested_role="realtor"
    )

    assert not decision.is_link


@pytest.mark.asyncio
async def test_a_blank_claimed_name_can_never_match() -> None:
    repo = _StubUserRepo(match=_match(full_name="Adaeze Okonkwo"))

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="", claimed_last_name="", requested_role="realtor"
    )

    assert not decision.is_link


@pytest.mark.asyncio
async def test_malformed_nin_is_no_match_and_never_reaches_the_database() -> None:
    repo = _StubUserRepo(match=_match())

    decision = await _service(repo).decide(
        nin="not-a-nin",
        claimed_first_name="Adaeze",
        claimed_last_name="Okonkwo",
        requested_role="realtor",
    )

    assert not decision.is_link
    assert repo.lookups == []


@pytest.mark.asyncio
async def test_a_role_the_person_already_holds_is_refused() -> None:
    """The feature exists so one person can be a seller AND a realtor, not so
    they can hold two seller accounts."""
    repo = _StubUserRepo(match=_match(), roles={"seller", "buyer"})

    with pytest.raises(RoleAlreadyHeld):
        await _service(repo).decide(
            nin=_NIN,
            claimed_first_name="Adaeze",
            claimed_last_name="Okonkwo",
            requested_role="seller",
        )


@pytest.mark.asyncio
async def test_linking_to_a_sibling_resolves_to_the_shared_root() -> None:
    """A chain must never form: the second hop has to land on the row that
    actually holds the NIN, so identity stays one lookup deep."""
    root_id = uuid4()
    sibling = _match()
    repo = _StubUserRepo(match=sibling, root_override=root_id)

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="Adaeze", claimed_last_name="Okonkwo", requested_role="buyer"
    )

    assert decision.root_user_id == root_id
    assert decision.root_user_id != sibling.user_id


@pytest.mark.asyncio
async def test_stored_parts_are_matched_exactly_not_by_splitting() -> None:
    """SCRUM-231. A compound surname the old token-splitter would have got
    wrong matches when both sides carry the parts as typed."""
    repo = _StubUserRepo(
        match=_match(full_name="Ada Van der Berg", first_name="Ada", last_name="Van der Berg")
    )

    decision = await _service(repo).decide(
        nin=_NIN,
        claimed_first_name="Ada",
        claimed_last_name="Van der Berg",
        requested_role="realtor",
    )

    assert decision.is_link


@pytest.mark.asyncio
async def test_a_pre_0019_root_still_matches_by_splitting() -> None:
    """A root that carries only full_name (no stored parts) falls back to the
    token split, so existing accounts keep linking after the migration."""
    repo = _StubUserRepo(match=_match(full_name="Adaeze Ngozi Okonkwo"))

    decision = await _service(repo).decide(
        nin=_NIN, claimed_first_name="Adaeze", claimed_last_name="Okonkwo", requested_role="realtor"
    )

    assert decision.is_link
