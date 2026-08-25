"""Unit tests for EmailSendService (SCRUM-81) — outcomes + retry signalling."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.ses_email import EmailError, InMemorySesClient
from app.repositories.notification_repo import NotificationRow
from app.services.email_send import EmailOutcome, EmailSendService

pytestmark = pytest.mark.asyncio

_UNSUB_BASE = "https://maihomme.com/notifications/unsubscribe"


def _row(*, channel: str = "email", sent_at: datetime | None = None) -> NotificationRow:
    return NotificationRow(
        id=uuid4(),
        user_id=uuid4(),
        channel=channel,
        type="document_verified",
        title="Document verified",
        body="Your document was verified.",
        reference_type="document",
        reference_id=uuid4(),
        is_read=False,
        sent_at=sent_at,
        read_at=None,
        created_at=datetime.now(UTC),
    )


class _StubNotifRepo:
    def __init__(self, row: NotificationRow | None) -> None:
        self._row = row
        self.marked: list[UUID] = []

    async def get_by_id(self, notification_id: UUID) -> NotificationRow | None:
        return self._row

    async def mark_sent(self, notification_id: UUID) -> bool:
        self.marked.append(notification_id)
        return True


class _StubUserRepo:
    def __init__(self, email: str | None) -> None:
        self._email = email

    async def get_email(self, user_id: UUID) -> str | None:
        return self._email


def _service(
    *, row: NotificationRow | None, email: str | None, client: InMemorySesClient
) -> tuple[EmailSendService, _StubNotifRepo]:
    repo = _StubNotifRepo(row)
    service = EmailSendService(
        notifications=repo,  # type: ignore[arg-type]
        users=_StubUserRepo(email),  # type: ignore[arg-type]
        email_client=client,
        unsubscribe_base_url=_UNSUB_BASE,
        unsubscribe_secret="test-secret",
    )
    return service, repo


async def test_sends_and_marks_sent() -> None:
    row = _row()
    client = InMemorySesClient()
    service, repo = _service(row=row, email="user@example.com", client=client)

    outcome = await service.send(row.id)

    assert outcome is EmailOutcome.SENT
    assert len(client.sent) == 1
    assert client.sent[0].to == "user@example.com"
    assert f"{_UNSUB_BASE}?uid={row.user_id}" in client.sent[0].text_body
    assert repo.marked == [row.id]


async def test_already_sent_is_noop() -> None:
    row = _row(sent_at=datetime.now(UTC))
    client = InMemorySesClient()
    service, repo = _service(row=row, email="user@example.com", client=client)

    assert await service.send(row.id) is EmailOutcome.ALREADY_SENT
    assert client.sent == []
    assert repo.marked == []


async def test_missing_row_is_not_found() -> None:
    client = InMemorySesClient()
    service, _ = _service(row=None, email="user@example.com", client=client)
    assert await service.send(uuid4()) is EmailOutcome.NOT_FOUND


async def test_non_email_row_is_skipped() -> None:
    row = _row(channel="sms")
    client = InMemorySesClient()
    service, _ = _service(row=row, email="user@example.com", client=client)
    assert await service.send(row.id) is EmailOutcome.NOT_EMAIL
    assert client.sent == []


async def test_no_email_on_file_is_terminal() -> None:
    row = _row()
    client = InMemorySesClient()
    service, repo = _service(row=row, email=None, client=client)

    assert await service.send(row.id) is EmailOutcome.NO_EMAIL
    assert client.sent == []
    assert repo.marked == []


async def test_ses_failure_raises_for_retry() -> None:
    row = _row()
    client = InMemorySesClient(fail_next=True)
    service, repo = _service(row=row, email="user@example.com", client=client)

    with pytest.raises(EmailError):
        await service.send(row.id)
    assert repo.marked == []
