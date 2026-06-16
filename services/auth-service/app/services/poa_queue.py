"""PoA review queue (SCRUM-56) — what the legal team sees.

Lists PoA submissions awaiting review (poa_verified_status='pending' with a
document on file), oldest-first. Read-only; the decision lives in
poa_review.py. No PII beyond the document owner-name is exposed in the queue —
the seller's phone is only read at decision time to send the notification.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.repositories.user_repo import PoaQueueRow, UserRepository


@dataclass(frozen=True)
class PoaQueuePage:
    items: list[PoaQueueRow]
    total: int
    page: int
    page_size: int


class PoaQueueService:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    async def list_pending(self, *, page: int = 1, page_size: int = 20) -> PoaQueuePage:
        items, total = await self._users.list_poa_queue(page=page, page_size=page_size)
        return PoaQueuePage(items=items, total=total, page=page, page_size=page_size)
