"""Save a buyer's optional "buying capacity" details (SCRUM-132).

The buyer onboarding "Personal Information" screen collects employment status,
preferred location, and budget — all optional ("Skip for now"). This persists
them to buyer_profiles for a just-verified buyer. Non-§11: a new table, no
users/transactions/escrow_ledger migration, no BVN/NIN storage. Budget arrives
in kobo (the frontend multiplies the naira figure by 100 per the money rule).
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.buyer_profile_repo import BuyerProfileRepository


class NotBuyer(RuntimeError):
    """Only buyer-role accounts have a buyer profile."""


class BuyerProfileService:
    def __init__(self, *, profiles: BuyerProfileRepository) -> None:
        self._profiles = profiles

    async def save(
        self,
        *,
        user_id: UUID,
        role: str,
        employment_status: str | None,
        preferred_location: str | None,
        budget_kobo: int | None,
    ) -> None:
        if role != "buyer":
            raise NotBuyer
        location = preferred_location.strip() if preferred_location else ""
        await self._profiles.upsert(
            user_id,
            employment_status=employment_status,
            preferred_location=location or None,
            budget_kobo=budget_kobo,
        )
