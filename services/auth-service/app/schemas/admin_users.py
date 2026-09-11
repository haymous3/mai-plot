"""Request/response models for admin user management (SCRUM-209)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.repositories.user_repo import AdminUserDetail, AdminUserRow

# Roles the list may be filtered to. Includes the staff roles so an admin can
# see who holds them — visibility is not the risk, granting them is, and this
# console cannot grant any role at all.
UserRoleFilter = Literal["buyer", "seller", "realtor", "bank_partner", "admin", "legal_team"]


class AdminUserListItem(BaseModel):
    """One row of the user list.

    ⚠️ No BVN/NIN, not even booleans: this is a browse surface over the whole
    user base, and the verification flags belong to a deliberate lookup of one
    person. The detail response carries them.
    """

    id: UUID
    role: str
    full_name: str | None
    email: str | None
    phone: str | None
    verified_status: str
    is_active: bool
    deleted: bool
    created_at: datetime
    # A realtor's Maihomme sign-in number (SCRUM-207), so a support call that
    # opens with "my number is MH-R-000123" can be matched to an account. Null
    # for every other role.
    registration_number: str | None

    @classmethod
    def from_row(cls, row: AdminUserRow) -> AdminUserListItem:
        return cls(
            id=row.id,
            role=row.role,
            full_name=row.full_name,
            email=row.email,
            phone=row.phone,
            verified_status=row.verified_status,
            is_active=row.is_active,
            # A boolean, not the timestamp: the list only needs to strike the row
            # through. The detail view carries when.
            deleted=row.deleted_at is not None,
            created_at=row.created_at,
            registration_number=row.registration_number,
        )


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    pagination: Pagination


class AdminUserDetailResponse(BaseModel):
    """One account in full.

    ⚠️ BVN and NIN are booleans. Both are stored as bcrypt hashes and neither the
    value nor the hash may leave the service — an 11-digit identifier is
    trivially crackable offline from its hash (§4). An admin needs to know
    whether we verified it, never what it is.
    """

    id: UUID
    role: str
    full_name: str | None
    email: str | None
    phone: str | None
    verified_status: str
    seller_authority_type: str | None
    poa_verified_status: str
    bvn_verified: bool
    nin_verified: bool
    location: str | None
    address: str | None
    is_active: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    registration_number: str | None

    @classmethod
    def from_detail(cls, detail: AdminUserDetail) -> AdminUserDetailResponse:
        return cls(
            id=detail.id,
            role=detail.role,
            full_name=detail.full_name,
            email=detail.email,
            phone=detail.phone,
            verified_status=detail.verified_status,
            seller_authority_type=detail.seller_authority_type,
            poa_verified_status=detail.poa_verified_status,
            bvn_verified=detail.bvn_verified,
            nin_verified=detail.nin_verified,
            location=detail.location,
            address=detail.address,
            is_active=detail.is_active,
            deleted_at=detail.deleted_at,
            created_at=detail.created_at,
            updated_at=detail.updated_at,
            registration_number=detail.registration_number,
        )


class AdminUserUpdateRequest(BaseModel):
    """The editable surface of a user account — and only that.

    Absent by design: `role`, `email`, `phone`. Role is a privilege-escalation
    path; email and phone are verified identifiers whose silent edit transfers
    account ownership and, for a realtor, breaks the MH-R login. `extra="ignore"`
    means a client that sends one is not rewarded with a 422 — it is simply not
    applied, so a stale form cannot half-work.

    Every field is optional, and `None` is meaningful for location/address: a
    caller that SENDS `null` clears the value, while one that omits the key
    leaves it alone. That distinction is why the service takes `set_*` flags.
    """

    model_config = ConfigDict(extra="ignore")

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _at_least_one(self) -> AdminUserUpdateRequest:
        if self.model_fields_set.isdisjoint({"full_name", "location", "address"}):
            raise ValueError("At least one of full_name, location or address is required.")
        return self

    @property
    def sent_location(self) -> bool:
        return "location" in self.model_fields_set

    @property
    def sent_address(self) -> bool:
        return "address" in self.model_fields_set


class AdminUserSuspendRequest(BaseModel):
    """Suspending needs a reason; reactivating does not.

    The reason lands in the audit row, and it is what a colleague reads when they
    find an account locked and have to decide whether to undo it.
    """

    model_config = ConfigDict(extra="ignore")

    reason: str = Field(min_length=1, max_length=500)


class AdminUserDeleteRequest(BaseModel):
    """A reason for the delete, recorded in the audit row.

    Optional so the endpoint stays usable without one, but the console always
    sends it: a soft-deleted account with no explanation is the row a colleague
    cannot act on later.
    """

    model_config = ConfigDict(extra="ignore")

    reason: str | None = Field(default=None, max_length=500)


class AdminUserDeleteResponse(BaseModel):
    message: str
    # Both true always, stated explicitly so the console can say what happened
    # rather than implying it. Soft delete releases the identifiers through the
    # partial unique indexes (migrations 0009/0010), so the person can sign up
    # again with the same email or phone.
    sessions_revoked: bool = True
    identifiers_released: bool = True


# --- NIN console (SCRUM-224) -------------------------------------------------
#
# The NIN is the one field the admin console may READ IN FULL, and only through
# the reveal endpoint below — never on the detail response, never on the list.
# ⚠️ Mandatory reasons. The reason is the audit row's answer to "why did this
# admin look at / change this person's national identity number", and a
# regulator reading the log later gets nothing from an empty one. Ten characters
# is the floor because "support" and "asked" are not reasons.

_REASON = Field(min_length=10, max_length=500)


class AdminNinStatusResponse(BaseModel):
    """The masked view. `recoverable` is false for a NIN verified before
    migration 0016 — there is a hash but nothing to decrypt, and the only
    remedy is Replace."""

    nin_verified: bool
    nin_last4: str | None
    nin_verified_at: datetime | None
    recoverable: bool


class AdminNinRevealRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str = _REASON


class AdminNinRevealResponse(BaseModel):
    """The only response in the platform that carries a NIN. The client shows
    it briefly and re-masks; it must not be persisted browser-side."""

    nin: str
    nin_last4: str


class AdminNinSetRequest(BaseModel):
    """Create or replace. The number is re-verified with the registry before
    anything is stored, exactly as the user's own submission is."""

    model_config = ConfigDict(extra="ignore")

    nin: str = Field(min_length=11, max_length=11)
    reason: str = _REASON


class AdminNinClearRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str = _REASON
