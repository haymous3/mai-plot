"""Read the caller's own account — GET /auth/me (SCRUM-188).

Every write endpoint for a user's details already existed (POST /auth/profile,
POST /auth/buyer/profile, the verify routes), but nothing could read them back.
That made a Settings screen impossible: it would have shown empty fields where
the user expects their current values, and it is why the onboarding "Personal
details" screen could not pre-fill either.

⚠️ WHAT THIS DELIBERATELY DOES NOT RETURN. BVN and NIN are exposed as
`bvn_verified` / `nin_verified` booleans, never as values or hashes. Both are
stored only as bcrypt hashes (CLAUDE.md §4); an 11-digit identifier is trivially
crackable offline from its hash, so the hash is as sensitive as the number. The
caller already knows their own BVN — what they need from us is whether we have
verified it.

Non-§11: a read of the caller's own row. No schema change, no financial data.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.buyer_profile_repo import BuyerProfileRepository
from app.repositories.realtor_registration_repo import RealtorRegistrationRepository
from app.repositories.user_repo import UserRepository


class AccountNotFound(RuntimeError):
    """No live account for this user id — soft-deleted or deactivated."""


@dataclass(frozen=True)
class Account:
    id: UUID
    role: str
    verified_status: str
    email: str | None
    phone: str
    full_name: str
    seller_authority_type: str | None
    poa_verified_status: str
    bvn_verified: bool
    nin_verified: bool
    # The private-bucket KEY. The ROUTE turns it into a short-lived pre-signed
    # URL; the key itself is never serialised to a client, so it stays useless
    # to anyone who does not already hold bucket credentials.
    avatar_s3_key: str | None
    # The account holder's OWN location (SCRUM-193). Every role has one, unlike
    # preferred_location below, which is where a BUYER wants to buy.
    location: str | None
    # Postal address (SCRUM-201). See migration 0014 for how it differs.
    address: str | None
    # Realtor-only (SCRUM-207): the Maihomme registration number they sign in
    # with. None for every other role, and for a realtor still awaiting
    # approval — the number is issued by the admin decision, not by onboarding.
    registration_number: str | None
    # Buyer-only; None for every other role, and for a buyer who has not filled
    # in the optional buying-capacity step.
    employment_status: str | None
    preferred_location: str | None
    budget_kobo: int | None


class AccountService:
    def __init__(
        self,
        *,
        users: UserRepository,
        buyer_profiles: BuyerProfileRepository,
        registration_numbers: RealtorRegistrationRepository,
    ) -> None:
        self._users = users
        self._buyer_profiles = buyer_profiles
        self._registration_numbers = registration_numbers

    async def get(self, user_id: UUID) -> Account:
        account = await self._users.get_account(user_id)
        if account is None:
            raise AccountNotFound

        # Only buyers have a buyer_profile row. Skipping the query for other
        # roles keeps a seller's /auth/me to a single read.
        employment_status = preferred_location = None
        budget_kobo = None
        if account.role == "buyer":
            profile = await self._buyer_profiles.get(user_id)
            if profile is not None:
                employment_status = profile.employment_status
                preferred_location = profile.preferred_location
                budget_kobo = profile.budget_kobo

        # Same reasoning as the buyer profile above: only realtors can have a
        # registration number, so no other role pays for the read.
        registration_number = None
        if account.role == "realtor":
            registration_number = await self._registration_numbers.get_for_user(user_id)

        return Account(
            id=account.id,
            role=account.role,
            verified_status=account.verified_status,
            email=account.email,
            phone=account.phone,
            full_name=account.full_name,
            seller_authority_type=account.seller_authority_type,
            poa_verified_status=account.poa_verified_status,
            bvn_verified=account.bvn_verified,
            nin_verified=account.nin_verified,
            avatar_s3_key=account.avatar_s3_key,
            location=account.location,
            address=account.address,
            registration_number=registration_number,
            employment_status=employment_status,
            preferred_location=preferred_location,
            budget_kobo=budget_kobo,
        )
