"""Declare a seller's selling authority after phone-OTP verification (SCRUM-132).

The onboarding "Seller Verification" screen collects the selling authority
(owner vs power_of_attorney) at the END of the funnel, whereas registration no
longer requires it up front. This lets a just-registered seller declare it using
the access token from /auth/otp/verify. A power_of_attorney declaration puts the
seller into the PoA review queue (gating the subsequent PoA-document upload);
an owner may then verify a NIN. Non-§11: writes users.seller_authority_type +
poa_verified_status, no schema migration and no BVN/NIN storage change.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.user_repo import UserRepository


class NotSeller(RuntimeError):
    """Only seller-role accounts may declare a selling authority."""


class SellerAuthorityService:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    async def set(self, *, user_id: UUID, role: str, authority_type: str) -> None:
        if role != "seller":
            raise NotSeller
        await self._users.set_seller_authority(user_id, authority_type=authority_type)
