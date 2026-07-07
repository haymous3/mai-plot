"""DB access for buyer_profiles (SCRUM-132).

Repository layer per CLAUDE.md §4 — route/service never touch SQLAlchemy
directly. One row per buyer; upsert keyed on user_id.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BuyerProfile


class BuyerProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        user_id: UUID,
        *,
        employment_status: str | None,
        preferred_location: str | None,
        budget_kobo: int | None,
    ) -> None:
        """Create or update the caller's buyer profile. Only overwrites a field
        when a non-None value is supplied, so a partial "Complete Profile" (or a
        later edit of one field) does not wipe the others."""
        stmt = select(BuyerProfile).where(BuyerProfile.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            self._session.add(
                BuyerProfile(
                    user_id=user_id,
                    employment_status=employment_status,
                    preferred_location=preferred_location,
                    budget_kobo=budget_kobo,
                )
            )
            return
        if employment_status is not None:
            row.employment_status = employment_status
        if preferred_location is not None:
            row.preferred_location = preferred_location
        if budget_kobo is not None:
            row.budget_kobo = budget_kobo
