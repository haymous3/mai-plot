"""Express interest in a listing (SCRUM-95).

The buyer taps "Express Interest" on the property detail page — lighter than an
offer. Idempotent; the first interest bumps the listing's interest_count. Non-§11
(no money/state-machine). An optional short message is trimmed and stored.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.interest_repo import InterestRepository

_MAX_MESSAGE = 1000


class ExpressInterestService:
    def __init__(self, *, interests: InterestRepository) -> None:
        self._interests = interests

    async def express(self, *, buyer_id: UUID, listing_id: UUID, message: str | None) -> bool:
        cleaned = message.strip()[:_MAX_MESSAGE] if message and message.strip() else None
        return await self._interests.express(
            buyer_id=buyer_id, listing_id=listing_id, message=cleaned
        )
