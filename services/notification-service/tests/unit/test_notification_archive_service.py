"""Unit tests for NotificationArchiveService (SCRUM-120)."""

from __future__ import annotations

import pytest

from app.services.notification_archive import NotificationArchiveService

pytestmark = pytest.mark.asyncio


class _StubRepo:
    def __init__(self, archived: int) -> None:
        self._archived = archived
        self.calls: list[dict[str, int]] = []

    async def archive_older_than(self, *, days: int, limit: int = 5000) -> int:
        self.calls.append({"days": days, "limit": limit})
        return self._archived


def _service(
    archived: int, *, retention_days: int = 90
) -> tuple[NotificationArchiveService, _StubRepo]:
    repo = _StubRepo(archived)
    svc = NotificationArchiveService(
        notifications=repo,  # type: ignore[arg-type]
        retention_days=retention_days,
    )
    return svc, repo


async def test_archives_and_reports_the_count() -> None:
    svc, repo = _service(7)

    result = await svc.run()

    assert result.archived == 7
    # The configured retention window is passed straight through.
    assert repo.calls == [{"days": 90, "limit": 5000}]


async def test_nothing_to_archive_is_a_noop() -> None:
    svc, _ = _service(0)

    result = await svc.run()

    assert result == type(result)(archived=0)


async def test_retention_window_is_configurable() -> None:
    svc, repo = _service(3, retention_days=30)

    await svc.run()

    assert repo.calls[0]["days"] == 30
