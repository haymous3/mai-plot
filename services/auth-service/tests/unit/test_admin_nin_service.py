"""AdminNinService (SCRUM-224) with stub repos + fake verifier."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.adapters.nin import InMemoryNinVerifier, NinVerificationOutcome
from app.repositories.user_repo import NinRecord
from app.security import CurrentUser
from app.services.admin_nin import (
    AdminNinService,
    NinBelongsToAnotherAccount,
    NinHeldByLinkedAccount,
    NinNotOnFile,
    NinNotRecoverable,
    NinRegistryUnavailable,
    NinRejectedByRegistry,
    UserDeleted,
    UserNotFound,
)
from app.services.nin import InvalidNinError, lookup_nin
from app.services.nin_crypto import build_nin_cipher

_PEPPER = "unit-test-nin-pepper"
# Obviously synthetic passphrases: GitGuardian scans every commit and flags a
# realistic-looking string literal as a "Generic Password" (it did, PR #230).
_CIPHER = build_nin_cipher(passphrase="a" * 40, env="local")
_NIN = "12345678901"
_OTHER_NIN = "98765432109"
_ADMIN = CurrentUser(user_id=uuid4(), role="admin")
_REASON = "Support ticket 4412: caller asked us to confirm identity."


class _StubUserRepo:
    """Just enough of UserRepository for the service: one account, mutable."""

    def __init__(
        self,
        *,
        exists: bool = True,
        deleted: bool = False,
        nin: str | None = None,
        recoverable: bool = True,
        other_owner_of: str | None = None,
        full_name: str = "Ada Lovelace",
        held_by: UUID | None = None,
    ) -> None:
        self.user_id = uuid4()
        self._exists = exists
        self._deleted = deleted
        # A linked second account (SCRUM-229): the NIN lives on `held_by`.
        self._held_by = held_by
        self._full_name = full_name
        self._nin_hash: str | None = "$2b$hash" if nin else None
        self._nin_encrypted: bytes | None = (
            _CIPHER.encrypt(nin, user_id=self.user_id) if nin and recoverable else None
        )
        self._nin_last4: str | None = nin[-4:] if nin else None
        self._lookup_owner: dict[str, UUID] = {}
        if nin:
            self._lookup_owner[lookup_nin(nin, pepper=_PEPPER)] = self.user_id
        if other_owner_of:
            self._lookup_owner[lookup_nin(other_owner_of, pepper=_PEPPER)] = uuid4()
        self.set_calls: list[dict[str, object]] = []
        self.clear_calls = 0

    async def get_nin_record(self, user_id: UUID) -> NinRecord | None:
        if not self._exists:
            return None
        return NinRecord(
            user_id=user_id,
            deleted_at=datetime.now(UTC) if self._deleted else None,
            has_nin=self._nin_hash is not None,
            # Mirrors the real repo: a sibling's record never carries the
            # ciphertext, even when the root's NIN is recoverable.
            nin_encrypted=None if self._held_by else self._nin_encrypted,
            nin_last4=self._nin_last4,
            nin_verified_at=datetime.now(UTC) if self._nin_hash else None,
            recoverable=self._nin_encrypted is not None,
            held_by_user_id=self._held_by,
        )

    async def get_account(self, user_id: UUID) -> SimpleNamespace | None:
        return SimpleNamespace(full_name=self._full_name)

    async def find_user_by_nin_lookup(self, nin_lookup: str) -> UUID | None:
        return self._lookup_owner.get(nin_lookup)

    async def set_nin_verified(
        self,
        user_id: UUID,
        *,
        nin_hash: str,
        nin_lookup: str,
        nin_encrypted: bytes,
        nin_last4: str,
    ) -> None:
        self.set_calls.append({"nin_hash": nin_hash, "nin_encrypted": nin_encrypted})
        self._nin_hash = nin_hash
        self._nin_encrypted = nin_encrypted
        self._nin_last4 = nin_last4

    async def clear_nin(self, user_id: UUID) -> bool:
        self.clear_calls += 1
        self._nin_hash = self._nin_encrypted = self._nin_last4 = None
        return True


class _StubAudit:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.rows.append(kwargs)


def _service(
    repo: _StubUserRepo, verifier: InMemoryNinVerifier | None = None
) -> tuple[AdminNinService, _StubAudit]:
    audit = _StubAudit()
    service = AdminNinService(
        users=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        verifier=verifier or InMemoryNinVerifier(),
        cipher=_CIPHER,
        pepper=_PEPPER,
    )
    return service, audit


# --- status ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_is_masked() -> None:
    repo = _StubUserRepo(nin=_NIN)
    service, audit = _service(repo)

    status = await service.get_status(user_id=repo.user_id)

    assert status.nin_verified is True
    assert status.nin_last4 == "8901"
    assert status.recoverable is True
    assert not hasattr(status, "nin")
    assert audit.rows == []  # the detail page read is what gets audited


@pytest.mark.asyncio
async def test_status_reports_pre_migration_rows_as_unrecoverable() -> None:
    repo = _StubUserRepo(nin=_NIN, recoverable=False)
    service, _ = _service(repo)
    status = await service.get_status(user_id=repo.user_id)
    assert status.nin_verified is True
    assert status.recoverable is False


@pytest.mark.asyncio
async def test_status_unknown_user() -> None:
    repo = _StubUserRepo(exists=False)
    service, _ = _service(repo)
    with pytest.raises(UserNotFound):
        await service.get_status(user_id=repo.user_id)


# --- reveal ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_reveal_returns_the_nin_and_audits_the_reason() -> None:
    repo = _StubUserRepo(nin=_NIN)
    service, audit = _service(repo)

    nin = await service.reveal(
        user_id=repo.user_id, admin=_ADMIN, reason=_REASON, ip_address="10.0.0.1"
    )

    assert nin == _NIN
    assert len(audit.rows) == 1
    row = audit.rows[0]
    assert row["action"] == "user.nin_revealed_by_admin"
    assert row["actor_id"] == _ADMIN.user_id
    assert row["entity_id"] == repo.user_id
    assert row["ip_address"] == "10.0.0.1"
    new_value = row["new_value"]
    assert isinstance(new_value, dict)
    assert new_value["reason"] == _REASON
    # The audit row names WHICH NIN by its last four, never the full number.
    assert new_value["nin_last4"] == "8901"
    assert _NIN not in str(new_value)


@pytest.mark.asyncio
async def test_reveal_works_on_a_deleted_account() -> None:
    """A regulator request does not stop at deletion."""
    repo = _StubUserRepo(nin=_NIN, deleted=True)
    service, _ = _service(repo)
    assert await service.reveal(user_id=repo.user_id, admin=_ADMIN, reason=_REASON) == _NIN


@pytest.mark.asyncio
async def test_reveal_refuses_when_nothing_on_file() -> None:
    repo = _StubUserRepo()
    service, audit = _service(repo)
    with pytest.raises(NinNotOnFile):
        await service.reveal(user_id=repo.user_id, admin=_ADMIN, reason=_REASON)
    assert audit.rows == []


@pytest.mark.asyncio
async def test_reveal_refuses_a_pre_migration_row() -> None:
    repo = _StubUserRepo(nin=_NIN, recoverable=False)
    service, audit = _service(repo)
    with pytest.raises(NinNotRecoverable):
        await service.reveal(user_id=repo.user_id, admin=_ADMIN, reason=_REASON)
    assert audit.rows == []


@pytest.mark.asyncio
async def test_reveal_refuses_a_blob_that_will_not_open() -> None:
    """Wrong key / wrong environment reads as not recoverable, not as a 500
    and not as an empty NIN."""
    repo = _StubUserRepo(nin=_NIN)
    other_key = build_nin_cipher(passphrase="b" * 40, env="local")
    repo._nin_encrypted = other_key.encrypt(_NIN, user_id=repo.user_id)
    service, audit = _service(repo)
    with pytest.raises(NinNotRecoverable):
        await service.reveal(user_id=repo.user_id, admin=_ADMIN, reason=_REASON)
    assert audit.rows == []


# --- set / replace --------------------------------------------------------


@pytest.mark.asyncio
async def test_set_creates_when_none_on_file() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier()
    service, audit = _service(repo, verifier)

    status = await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin=_NIN, reason=_REASON)

    assert verifier.calls == 1
    # The account's own name is what the registry match scores against.
    assert (verifier.last_first_name, verifier.last_last_name) == ("Ada", "Lovelace")
    assert len(repo.set_calls) == 1
    assert repo.set_calls[0]["nin_hash"] != _NIN
    assert status.nin_verified and status.recoverable and status.nin_last4 == "8901"
    row = audit.rows[0]
    assert row["action"] == "user.nin_set_by_admin"
    assert row["old_value"] == {"nin_verified": False, "nin_last4": None}
    assert row["new_value"] == {"nin_verified": True, "nin_last4": "8901", "reason": _REASON}
    assert _NIN not in str(row)


@pytest.mark.asyncio
async def test_set_replaces_an_existing_nin() -> None:
    """Unlike the user's own path, an existing NIN is overwritten, not 409'd."""
    repo = _StubUserRepo(nin=_NIN)
    service, audit = _service(repo)

    status = await service.set_nin(
        user_id=repo.user_id, admin=_ADMIN, nin=_OTHER_NIN, reason=_REASON
    )

    assert status.nin_last4 == "2109"
    assert await service.reveal(user_id=repo.user_id, admin=_ADMIN, reason=_REASON) == _OTHER_NIN
    old = audit.rows[0]["old_value"]
    assert isinstance(old, dict) and old["nin_last4"] == "8901"


@pytest.mark.asyncio
async def test_set_makes_a_pre_migration_row_recoverable() -> None:
    repo = _StubUserRepo(nin=_NIN, recoverable=False)
    service, _ = _service(repo)
    status = await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin=_NIN, reason=_REASON)
    assert status.recoverable is True


@pytest.mark.asyncio
async def test_set_refuses_a_nin_another_account_owns() -> None:
    repo = _StubUserRepo(other_owner_of=_OTHER_NIN)
    verifier = InMemoryNinVerifier()
    service, audit = _service(repo, verifier)
    with pytest.raises(NinBelongsToAnotherAccount):
        await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin=_OTHER_NIN, reason=_REASON)
    assert verifier.calls == 0  # refused before spending a registry call
    assert repo.set_calls == [] and audit.rows == []


@pytest.mark.asyncio
async def test_set_refuses_a_registry_rejection_and_stores_nothing() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier(
        outcome=NinVerificationOutcome(status="failed", mismatches=("last_name",))
    )
    service, audit = _service(repo, verifier)
    with pytest.raises(NinRejectedByRegistry) as excinfo:
        await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin=_NIN, reason=_REASON)
    assert excinfo.value.status == "failed"
    assert excinfo.value.mismatches == ("last_name",)
    assert repo.set_calls == [] and audit.rows == []


@pytest.mark.asyncio
async def test_set_surfaces_registry_outage() -> None:
    repo = _StubUserRepo()
    verifier = InMemoryNinVerifier(fail_next=True)
    service, _ = _service(repo, verifier)
    with pytest.raises(NinRegistryUnavailable):
        await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin=_NIN, reason=_REASON)
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_set_refuses_bad_format_before_anything_else() -> None:
    repo = _StubUserRepo(exists=False)
    service, _ = _service(repo)
    with pytest.raises(InvalidNinError):
        await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin="123", reason=_REASON)


@pytest.mark.asyncio
async def test_set_refuses_a_deleted_account() -> None:
    repo = _StubUserRepo(deleted=True)
    service, _ = _service(repo)
    with pytest.raises(UserDeleted):
        await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin=_NIN, reason=_REASON)


# --- clear ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_removes_and_audits() -> None:
    repo = _StubUserRepo(nin=_NIN)
    service, audit = _service(repo)

    status = await service.clear_nin(user_id=repo.user_id, admin=_ADMIN, reason=_REASON)

    assert repo.clear_calls == 1
    assert status.nin_verified is False and status.nin_last4 is None
    row = audit.rows[0]
    assert row["action"] == "user.nin_cleared_by_admin"
    assert row["old_value"] == {"nin_verified": True, "nin_last4": "8901"}
    assert row["new_value"] == {"nin_verified": False, "reason": _REASON}


@pytest.mark.asyncio
async def test_clear_refuses_when_nothing_on_file() -> None:
    repo = _StubUserRepo()
    service, audit = _service(repo)
    with pytest.raises(NinNotOnFile):
        await service.clear_nin(user_id=repo.user_id, admin=_ADMIN, reason=_REASON)
    assert repo.clear_calls == 0 and audit.rows == []


@pytest.mark.asyncio
async def test_clear_refuses_a_deleted_account() -> None:
    repo = _StubUserRepo(nin=_NIN, deleted=True)
    service, _ = _service(repo)
    with pytest.raises(UserDeleted):
        await service.clear_nin(user_id=repo.user_id, admin=_ADMIN, reason=_REASON)


# ---------------------------------------------------------------------------
# Linked second accounts (SCRUM-229)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_of_a_linked_account_reports_the_roots_nin() -> None:
    """The detail page one screen up says "verified"; the console must not
    then say "no NIN on file"."""
    root = uuid4()
    repo = _StubUserRepo(nin="12345678901", held_by=root)
    service, _ = _service(repo)
    status = await service.get_status(user_id=repo.user_id)

    assert status.nin_verified is True
    assert status.nin_last4 == "8901"
    assert status.recoverable is True
    assert status.held_by_user_id == root


@pytest.mark.asyncio
async def test_reveal_on_a_linked_account_is_refused_and_names_the_root() -> None:
    """Refused ON PURPOSE: the reveal audit must be written against the row
    that holds the number, and the sibling's record carries no ciphertext."""
    root = uuid4()
    repo = _StubUserRepo(nin="12345678901", held_by=root)

    service, _ = _service(repo)
    with pytest.raises(NinHeldByLinkedAccount) as exc:
        await service.reveal(user_id=repo.user_id, admin=_ADMIN, reason="support call")
    assert exc.value.held_by == root


@pytest.mark.asyncio
async def test_set_on_a_linked_account_is_refused_before_any_registry_call() -> None:
    """Writing a NIN onto a sibling could only collide with the root's under
    the unique index; refuse before spending a registry call on it."""
    root = uuid4()
    repo = _StubUserRepo(nin="12345678901", held_by=root)
    verifier = InMemoryNinVerifier()

    service, _ = _service(repo, verifier=verifier)
    with pytest.raises(NinHeldByLinkedAccount):
        await service.set_nin(user_id=repo.user_id, admin=_ADMIN, nin="99999999999", reason="typo")
    assert verifier.calls == 0
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_clear_on_a_linked_account_is_refused() -> None:
    root = uuid4()
    repo = _StubUserRepo(nin="12345678901", held_by=root)

    service, _ = _service(repo)
    with pytest.raises(NinHeldByLinkedAccount):
        await service.clear_nin(user_id=repo.user_id, admin=_ADMIN, reason="x")
    assert repo.clear_calls == 0
