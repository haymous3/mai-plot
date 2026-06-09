"""BvnVerificationService with stub repo + fake verifier."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.bvn import BvnVerificationOutcome, InMemoryBvnVerifier
from app.services.bvn import InvalidBvnError, lookup_bvn
from app.services.bvn_verification import (
    BvnAlreadyVerified,
    BvnVerificationService,
    BvnVerificationUnavailable,
)

_PEPPER = "unit-test-pepper"
_BVN = "12345678901"


class _StubUserRepo:
    def __init__(self, *, has_bvn: bool = False, lookup_owner: UUID | None = None) -> None:
        self._has_bvn = has_bvn
        self._lookup_owner = lookup_owner
        self.set_calls: list[dict[str, object]] = []

    async def has_bvn(self, user_id: UUID) -> bool:
        return self._has_bvn

    async def find_user_by_bvn_lookup(self, bvn_lookup: str) -> UUID | None:
        return self._lookup_owner

    async def set_bvn_verified(self, user_id: UUID, *, bvn_hash: str, bvn_lookup: str) -> None:
        self.set_calls.append({"user_id": user_id, "bvn_hash": bvn_hash, "bvn_lookup": bvn_lookup})


def _service(repo: _StubUserRepo, verifier: InMemoryBvnVerifier) -> BvnVerificationService:
    return BvnVerificationService(
        users=repo,  # type: ignore[arg-type]
        verifier=verifier,
        pepper=_PEPPER,
    )


@pytest.mark.asyncio
async def test_happy_path_hashes_and_stores() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryBvnVerifier()
    result = await _service(repo, verifier).verify(user_id=uuid4(), bvn=_BVN)

    assert result.status == "verified"
    assert verifier.calls == 1
    assert len(repo.set_calls) == 1
    call = repo.set_calls[0]
    # Stored values are derived, never the raw BVN.
    assert call["bvn_hash"] != _BVN
    assert str(call["bvn_hash"]).startswith("$2")
    assert call["bvn_lookup"] == lookup_bvn(_BVN, pepper=_PEPPER)


@pytest.mark.asyncio
async def test_invalid_format_raises_before_any_call() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryBvnVerifier()
    with pytest.raises(InvalidBvnError):
        await _service(repo, verifier).verify(user_id=uuid4(), bvn="123")
    assert verifier.calls == 0
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_user_already_has_bvn_conflicts() -> None:
    repo = _StubUserRepo(has_bvn=True)
    verifier = InMemoryBvnVerifier()
    with pytest.raises(BvnAlreadyVerified):
        await _service(repo, verifier).verify(user_id=uuid4(), bvn=_BVN)
    assert verifier.calls == 0


@pytest.mark.asyncio
async def test_bvn_owned_by_another_account_conflicts() -> None:
    repo = _StubUserRepo(lookup_owner=uuid4())
    verifier = InMemoryBvnVerifier()
    with pytest.raises(BvnAlreadyVerified):
        await _service(repo, verifier).verify(user_id=uuid4(), bvn=_BVN)
    assert verifier.calls == 0
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_bureau_failure_is_unavailable() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryBvnVerifier(fail_next=True)
    with pytest.raises(BvnVerificationUnavailable):
        await _service(repo, verifier).verify(user_id=uuid4(), bvn=_BVN)
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_not_verified_result_does_not_store() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryBvnVerifier(outcome=BvnVerificationOutcome(status="failed"))
    result = await _service(repo, verifier).verify(user_id=uuid4(), bvn=_BVN)
    assert result.status == "failed"
    assert repo.set_calls == []
