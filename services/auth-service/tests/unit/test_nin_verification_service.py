"""NinVerificationService with stub repo + fake verifier."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.adapters.nin import InMemoryNinVerifier, NinVerificationOutcome
from app.repositories.user_repo import UserAuthority
from app.services.nin import InvalidNinError, lookup_nin
from app.services.nin_verification import (
    NinAlreadyVerified,
    NinVerificationService,
    NinVerificationUnavailable,
)

_PEPPER = "unit-test-nin-pepper"
_NIN = "12345678901"
_OWNER = UserAuthority(role="seller", seller_authority_type="owner")


class _StubUserRepo:
    def __init__(
        self,
        *,
        authority: UserAuthority | None = _OWNER,
        has_nin: bool = False,
        lookup_owner: UUID | None = None,
        full_name: str | None = "",
    ) -> None:
        self._authority = authority
        self._has_nin = has_nin
        self._lookup_owner = lookup_owner
        self._full_name = full_name
        self.set_calls: list[dict[str, object]] = []

    async def get_authority(self, user_id: UUID) -> UserAuthority | None:
        return self._authority

    async def get_account(self, user_id: UUID) -> SimpleNamespace | None:
        """Only `full_name` is read by the service; a None stands for an
        account row the service cannot see at all."""
        if self._full_name is None:
            return None
        return SimpleNamespace(full_name=self._full_name)

    async def has_nin(self, user_id: UUID) -> bool:
        return self._has_nin

    async def find_user_by_nin_lookup(self, nin_lookup: str) -> UUID | None:
        return self._lookup_owner

    async def set_nin_verified(self, user_id: UUID, *, nin_hash: str, nin_lookup: str) -> None:
        self.set_calls.append({"user_id": user_id, "nin_hash": nin_hash, "nin_lookup": nin_lookup})


def _service(repo: _StubUserRepo, verifier: InMemoryNinVerifier) -> NinVerificationService:
    return NinVerificationService(
        users=repo,  # type: ignore[arg-type]
        verifier=verifier,
        pepper=_PEPPER,
    )


@pytest.mark.asyncio
async def test_happy_path_hashes_and_stores() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier()
    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    assert result.status == "verified"
    assert verifier.calls == 1
    assert len(repo.set_calls) == 1
    call = repo.set_calls[0]
    assert call["nin_hash"] != _NIN
    assert str(call["nin_hash"]).startswith("$2")
    assert call["nin_lookup"] == lookup_nin(_NIN, pepper=_PEPPER)


@pytest.mark.asyncio
async def test_a_buyer_can_verify_a_nin() -> None:
    """SCRUM-189 removed the owner-seller gate. A buyer used to be hard-403'd
    here, which is why buyer onboarding collected a BVN instead."""
    repo = _StubUserRepo(authority=UserAuthority(role="buyer", seller_authority_type=None))
    verifier = InMemoryNinVerifier()

    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    assert result.status == "verified"
    assert len(repo.set_calls) == 1


@pytest.mark.asyncio
async def test_a_poa_seller_can_verify_a_nin() -> None:
    """This one was a live bug, not just a limitation: seller onboarding
    already asked every seller for a NIN, so a PoA seller hit 403 on a step
    the funnel required of them."""
    repo = _StubUserRepo(
        authority=UserAuthority(role="seller", seller_authority_type="power_of_attorney")
    )
    verifier = InMemoryNinVerifier()

    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    assert result.status == "verified"


@pytest.mark.asyncio
async def test_a_realtor_can_verify_a_nin() -> None:
    repo = _StubUserRepo(authority=UserAuthority(role="realtor", seller_authority_type=None))
    verifier = InMemoryNinVerifier()

    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    assert result.status == "verified"


@pytest.mark.asyncio
async def test_format_is_still_validated_before_the_bureau_is_called() -> None:
    """Dropping the role gate must not drop input validation with it."""
    repo = _StubUserRepo(authority=UserAuthority(role="buyer", seller_authority_type=None))
    verifier = InMemoryNinVerifier()

    with pytest.raises(InvalidNinError):
        await _service(repo, verifier).verify(user_id=uuid4(), nin="bad")

    assert verifier.calls == 0
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_invalid_format_raises_for_eligible_user() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier()
    with pytest.raises(InvalidNinError):
        await _service(repo, verifier).verify(user_id=uuid4(), nin="123")
    assert verifier.calls == 0


@pytest.mark.asyncio
async def test_user_already_has_nin_conflicts() -> None:
    repo = _StubUserRepo(has_nin=True)
    with pytest.raises(NinAlreadyVerified):
        await _service(repo, InMemoryNinVerifier()).verify(user_id=uuid4(), nin=_NIN)


@pytest.mark.asyncio
async def test_nin_owned_by_another_account_conflicts() -> None:
    repo = _StubUserRepo(lookup_owner=uuid4())
    verifier = InMemoryNinVerifier()
    with pytest.raises(NinAlreadyVerified):
        await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)
    assert verifier.calls == 0
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_bureau_failure_is_unavailable() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier(fail_next=True)
    with pytest.raises(NinVerificationUnavailable):
        await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_not_verified_result_does_not_store() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier(outcome=NinVerificationOutcome(status="failed"))
    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)
    assert result.status == "failed"
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_review_outcome_is_pending_and_does_not_store() -> None:
    """Ninja's `review` must not advance the account. It is a partial name
    match, so nothing is persisted and the caller can retry."""
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier(
        outcome=NinVerificationOutcome(status="pending", mismatches=("last_name",))
    )
    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)
    assert result.status == "pending"
    assert result.mismatches == ("last_name",)
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_account_name_is_split_and_sent_to_the_registry() -> None:
    repo = _StubUserRepo(full_name="Adaeze Ngozi Okonkwo")
    verifier = InMemoryNinVerifier()
    await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    # First and last token; the middle name is deliberately not guessed at.
    assert verifier.last_first_name == "Adaeze"
    assert verifier.last_last_name == "Okonkwo"


@pytest.mark.asyncio
async def test_account_name_wins_over_the_submitted_one() -> None:
    """The name on the account is the one the deal documents carry, so a
    request cannot talk the match into scoring against something else."""
    repo = _StubUserRepo(full_name="Adaeze Okonkwo")
    verifier = InMemoryNinVerifier()
    await _service(repo, verifier).verify(
        user_id=uuid4(), nin=_NIN, first_name="Someone", last_name="Else"
    )

    assert verifier.last_first_name == "Adaeze"
    assert verifier.last_last_name == "Okonkwo"


@pytest.mark.asyncio
async def test_submitted_name_is_used_when_the_account_has_none() -> None:
    """Onboarding verifies the NIN BEFORE it writes the profile, so full_name
    is still the empty-string default at this point."""
    repo = _StubUserRepo(full_name="")
    verifier = InMemoryNinVerifier()
    await _service(repo, verifier).verify(
        user_id=uuid4(), nin=_NIN, first_name="  Adaeze ", last_name=" Okonkwo "
    )

    assert verifier.last_first_name == "Adaeze"
    assert verifier.last_last_name == "Okonkwo"


@pytest.mark.asyncio
async def test_no_name_anywhere_degrades_to_an_existence_check() -> None:
    """A phone+OTP account that never filled in a profile has no name at all.
    That is not an error — the NIN is still checked for existence."""
    repo = _StubUserRepo(full_name="")
    verifier = InMemoryNinVerifier()
    result = await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    assert verifier.last_first_name is None
    assert verifier.last_last_name is None
    assert result.status == "verified"


@pytest.mark.asyncio
async def test_single_token_name_sends_only_a_first_name() -> None:
    repo = _StubUserRepo(full_name="Okonkwo")
    verifier = InMemoryNinVerifier()
    await _service(repo, verifier).verify(user_id=uuid4(), nin=_NIN)

    assert verifier.last_first_name == "Okonkwo"
    assert verifier.last_last_name is None
