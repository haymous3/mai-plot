"""Unit tests for PayoutAccountService (SCRUM-145)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.paystack_recipient import PaystackRecipientError, RecipientResult
from app.repositories.payout_account_repo import PayoutAccountRow
from app.services.payout_account import PayoutAccountService

pytestmark = pytest.mark.asyncio


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
    def __init__(self, *, code: str = "RCP_TEST_1234", fail: bool = False) -> None:
        self._code = code
        self._fail = fail
        self.calls = 0

    async def create_recipient(
        self, *, account_number: str, bank_code: str, account_name: str
    ) -> RecipientResult:
        self.calls += 1
        if self._fail:
            raise PaystackRecipientError("boom")
        return RecipientResult(recipient_code=self._code)


async def test_set_account_creates_recipient_then_persists() -> None:
    repo = _StubRepo()
    client = _StubRecipientClient(code="RCP_TEST_9999")
    svc = PayoutAccountService(accounts=repo, recipient_client=client)  # type: ignore[arg-type]

    user = uuid4()
    row = await svc.set_account(
        user_id=user, account_number="0123456789", bank_code="058", account_name="Ada A"
    )

    assert client.calls == 1
    assert repo.upserted is not None
    assert repo.upserted["recipient_code"] == "RCP_TEST_9999"
    assert row.recipient_code == "RCP_TEST_9999"
    assert row.account_number == "0123456789"


async def test_set_account_propagates_recipient_error_and_skips_write() -> None:
    repo = _StubRepo()
    client = _StubRecipientClient(fail=True)
    svc = PayoutAccountService(accounts=repo, recipient_client=client)  # type: ignore[arg-type]

    with pytest.raises(PaystackRecipientError):
        await svc.set_account(
            user_id=uuid4(), account_number="0123456789", bank_code="058", account_name="Ada A"
        )
    assert repo.upserted is None  # never persisted when the recipient fails


async def test_get_account_returns_existing() -> None:
    existing = PayoutAccountRow(
        id=uuid4(),
        user_id=uuid4(),
        account_number="0123456789",
        bank_code="058",
        account_name="Ada A",
        recipient_code="RCP_X",
    )
    svc = PayoutAccountService(
        accounts=_StubRepo(existing=existing),  # type: ignore[arg-type]
        recipient_client=_StubRecipientClient(),
    )
    assert await svc.get_account(existing.user_id) is existing
