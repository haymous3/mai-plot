"""Unit tests for PayoutAccountService (SCRUM-145; bank-resolved name, audit and
change alert since SCRUM-223)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.paystack_recipient import (
    AccountNotResolved,
    PaystackRecipientError,
    RecipientResult,
    ResolvedAccount,
)
from app.repositories.payout_account_repo import PayoutAccountRow
from app.services.payout_account import PayoutAccountService
from app.services.payout_notifier import change_message

pytestmark = pytest.mark.asyncio

_BANK_NAME = "ADAEZE OKONKWO"


class _StubRepo:
    def __init__(self, *, existing: PayoutAccountRow | None = None) -> None:
        self._existing = existing
        self.upserted: dict[str, object] | None = None

    async def get(self, user_id: UUID) -> PayoutAccountRow | None:
        return self._existing

    async def upsert(
        self,
        *,
        user_id: UUID,
        account_number: str,
        bank_code: str,
        account_name: str,
        recipient_code: str | None,
    ) -> PayoutAccountRow:
        self.upserted = {
            "user_id": user_id,
            "account_number": account_number,
            "bank_code": bank_code,
            "account_name": account_name,
            "recipient_code": recipient_code,
        }
        return PayoutAccountRow(
            id=uuid4(),
            user_id=user_id,
            account_number=account_number,
            bank_code=bank_code,
            account_name=account_name,
            recipient_code=recipient_code,
        )


class _StubRecipientClient:
    def __init__(
        self,
        *,
        code: str = "RCP_TEST_1234",
        fail: bool = False,
        unresolved: bool = False,
        resolve_down: bool = False,
    ) -> None:
        self._code = code
        self._fail = fail
        self._unresolved = unresolved
        self._resolve_down = resolve_down
        self.calls = 0
        self.recipient_names: list[str] = []

    async def create_recipient(
        self, *, account_number: str, bank_code: str, account_name: str
    ) -> RecipientResult:
        self.calls += 1
        self.recipient_names.append(account_name)
        if self._fail:
            raise PaystackRecipientError("boom")
        return RecipientResult(recipient_code=self._code)

    async def resolve_account(self, *, account_number: str, bank_code: str) -> ResolvedAccount:
        if self._resolve_down:
            raise PaystackRecipientError("resolve down")
        if self._unresolved:
            raise AccountNotResolved()
        return ResolvedAccount(account_name=_BANK_NAME)


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _StubNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def account_changed(self, *, user_id: UUID, account_last4: str, first_time: bool) -> None:
        self.calls.append(
            {"user_id": user_id, "account_last4": account_last4, "first_time": first_time}
        )


def _svc(
    repo: _StubRepo | None = None, client: _StubRecipientClient | None = None
) -> tuple[PayoutAccountService, _StubRepo, _StubRecipientClient, _StubAudit, _StubNotifier]:
    repo = repo or _StubRepo()
    client = client or _StubRecipientClient()
    audit, notifier = _StubAudit(), _StubNotifier()
    svc = PayoutAccountService(
        accounts=repo,  # type: ignore[arg-type]
        recipient_client=client,
        audit=audit,  # type: ignore[arg-type]
        notifier=notifier,
    )
    return svc, repo, client, audit, notifier


def _existing(user_id: UUID) -> PayoutAccountRow:
    return PayoutAccountRow(
        id=uuid4(),
        user_id=user_id,
        account_number="9876543210",
        bank_code="044",
        account_name="OLD NAME",
        recipient_code="RCP_OLD",
    )


async def test_set_account_creates_recipient_then_persists() -> None:
    svc, repo, client, _, _ = _svc(client=_StubRecipientClient(code="RCP_TEST_9999"))

    row = await svc.set_account(
        user_id=uuid4(), actor_role="seller", account_number="0123456789", bank_code="058"
    )

    assert client.calls == 1
    assert repo.upserted is not None
    assert repo.upserted["recipient_code"] == "RCP_TEST_9999"
    assert row.recipient_code == "RCP_TEST_9999"
    assert row.account_number == "0123456789"


async def test_the_stored_and_recipient_name_is_the_banks() -> None:
    """SCRUM-223: nothing typed reaches the row or Paystack — only the bank's name."""
    svc, repo, client, _, _ = _svc()

    await svc.set_account(
        user_id=uuid4(), actor_role="seller", account_number="0123456789", bank_code="058"
    )

    assert repo.upserted is not None
    assert repo.upserted["account_name"] == _BANK_NAME
    assert client.recipient_names == [_BANK_NAME]


async def test_an_unknown_account_is_refused_before_anything_is_created() -> None:
    svc, repo, client, audit, notifier = _svc(client=_StubRecipientClient(unresolved=True))

    with pytest.raises(AccountNotResolved):
        await svc.set_account(
            user_id=uuid4(), actor_role="seller", account_number="0123450000", bank_code="058"
        )
    assert client.calls == 0
    assert repo.upserted is None
    assert audit.records == [] and notifier.calls == []


async def test_set_account_propagates_recipient_error_and_skips_write() -> None:
    svc, repo, _, audit, notifier = _svc(client=_StubRecipientClient(fail=True))

    with pytest.raises(PaystackRecipientError):
        await svc.set_account(
            user_id=uuid4(), actor_role="seller", account_number="0123456789", bank_code="058"
        )
    assert repo.upserted is None  # never persisted when the recipient fails
    assert audit.records == [] and notifier.calls == []


async def test_a_resolve_outage_is_a_rail_error_not_a_bad_number() -> None:
    svc, repo, _, _, _ = _svc(client=_StubRecipientClient(resolve_down=True))

    with pytest.raises(PaystackRecipientError):
        await svc.set_account(
            user_id=uuid4(), actor_role="seller", account_number="0123456789", bank_code="058"
        )
    assert repo.upserted is None


async def test_first_account_is_audited_and_announced_without_the_full_number() -> None:
    user = uuid4()
    svc, _, _, audit, notifier = _svc()

    row = await svc.set_account(
        user_id=user, actor_role="seller", account_number="0123456789", bank_code="058"
    )

    [record] = audit.records
    assert record["action"] == "payout_account.updated"
    assert record["entity_id"] == row.id
    assert record["old_value"] is None
    assert record["new_value"] == {"bank_code": "058", "account_last4": "6789"}
    assert "0123456789" not in repr(record)
    assert notifier.calls == [{"user_id": user, "account_last4": "6789", "first_time": True}]


async def test_a_change_records_what_it_replaced() -> None:
    user = uuid4()
    svc, _, _, audit, notifier = _svc(repo=_StubRepo(existing=_existing(user)))

    await svc.set_account(
        user_id=user, actor_role="seller", account_number="0123456789", bank_code="058"
    )

    assert audit.records[0]["old_value"] == {"bank_code": "044", "account_last4": "3210"}
    assert notifier.calls[0]["first_time"] is False


async def test_resolve_name_returns_the_banks_name() -> None:
    svc, _, _, _, _ = _svc()
    assert await svc.resolve_name(account_number="0123456789", bank_code="058") == _BANK_NAME


async def test_get_account_returns_existing() -> None:
    existing = _existing(uuid4())
    svc, _, _, _, _ = _svc(repo=_StubRepo(existing=existing))
    assert await svc.get_account(existing.user_id) is existing


async def test_the_change_email_warns_the_reader_who_did_not_make_it() -> None:
    title, body = change_message(account_last4="6789", first_time=False)
    assert "changed" in title
    assert "6789" in body and "If this wasn't you" in body
