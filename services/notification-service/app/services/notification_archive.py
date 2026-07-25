"""Archive notifications older than the retention window (SCRUM-120).

A Celery beat runs this daily: notifications past `retention_days` are stamped
`archived_at` so they drop out of the in-app centre (its reads filter
archived_at IS NULL) and the table stays lean. Rows are retained, not deleted —
archiving is reversible and keeps an audit trail. Idempotent + batched: the repo
query only touches still-live rows, up to a cap per run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.repositories.notification_repo import NotificationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchiveResult:
    archived: int


class NotificationArchiveService:
    def __init__(
        self,
        *,
        notifications: NotificationRepository,
        retention_days: int,
        batch_limit: int = 5000,
    ) -> None:
        self._notifications = notifications
        self._retention_days = retention_days
        self._batch_limit = batch_limit

    async def run(self) -> ArchiveResult:
        archived = await self._notifications.archive_older_than(
            days=self._retention_days, limit=self._batch_limit
        )
        if archived:
            logger.info("notifications.archived", extra={"count": archived})
        return ArchiveResult(archived=archived)
