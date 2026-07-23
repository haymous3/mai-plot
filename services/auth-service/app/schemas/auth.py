"""Request/response models for the /auth endpoints.

Field shapes mirror api-contracts.md §Auth Service. The `password` field
on RegisterRequest is accepted but ignored — see CLAUDE.md / SCRUM-43:
password storage requires a data-model migration that ships with the
/auth/login ticket, not this one.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.validators.email import InvalidEmailError, normalise_email
from app.validators.phone import InvalidPhoneError, normalise_nigerian_phone

# Roles a user may SELF-REGISTER as via POST /auth/register. Deliberately
# narrow — the public endpoint must never be able to mint a privileged account.
Role = Literal["seller", "buyer", "realtor"]
# Every role the DB may hold (mirrors the users_role_check constraint). Used on
# response bodies, where the account's actual role is reflected back — including
# admin/legal_team/bank_partner accounts, which are provisioned out-of-band, not
# through registration. Keeping this separate from `Role` is what stops the
# login response from 500-ing on an admin account (SCRUM-151).
AccountRole = Literal["seller", "buyer", "realtor", "bank_partner", "admin", "legal_team"]
SellerAuthorityType = Literal["owner", "power_of_attorney"]
OtpPurpose = Literal["registration", "login"]
# Purposes an email magic link may serve (mirrors the email_verification_tokens
# purpose CHECK). Only 'registration' is issued today; login/reset are reserved.
EmailVerifyPurpose = Literal["registration", "login", "reset"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phone: str
    role: Role
    # email is now REQUIRED and is the account verification channel (SCRUM-152 —
    # replaced phone OTP). Normalised + format-checked below so the verification
    # email has a clean target and the users.email unique constraint holds.
    email: str = Field(max_length=254)
    # password is optional at register; when supplied it is stored so the user
    # can log in via email/password (SCRUM-45).
    password: str | None = Field(default=None, min_length=8, max_length=128)
    # full_name is optional at register (SCRUM-155): the funnel collects it up
    # front now that there is no post-OTP session step to capture it. Persisted
    # to user_pii via create_with_pii; blank-after-strip is treated as absent.
    full_name: str | None = Field(default=None, max_length=120)
    seller_authority_type: SellerAuthorityType | None = None

    @model_validator(mode="after")
    def _normalise_and_check_seller(self) -> RegisterRequest:
        try:
            object.__setattr__(self, "phone", normalise_nigerian_phone(self.phone))
        except InvalidPhoneError as exc:
            raise ValueError(str(exc)) from exc

        try:
            object.__setattr__(self, "email", normalise_email(self.email))
        except InvalidEmailError as exc:
            raise ValueError(str(exc)) from exc

        # Trim the display name; collapse a blank/whitespace value to None so the
        # repo stores "" rather than stray spaces.
        trimmed_name = self.full_name.strip() if self.full_name else ""
        object.__setattr__(self, "full_name", trimmed_name or None)

        # A seller may register without declaring authority yet — it is collected
        # later on the "Seller Verification" onboarding screen via
        # POST /auth/seller/authority (SCRUM-132). Non-sellers still may not send
        # it. When a seller does supply it at register, it is honoured.
        if self.role != "seller" and self.seller_authority_type is not None:
            raise ValueError("seller_authority_type is only allowed when role=seller")
        return self


class RegisterResponse(BaseModel):
    user_id: UUID
    message: str
    # Seconds until the emailed magic link expires (SCRUM-152). Renamed from
    # otp_expires_in_seconds when verification moved from SMS OTP to email.
    verification_expires_in_seconds: int


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phone: str
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    purpose: OtpPurpose = "registration"

    @model_validator(mode="after")
    def _normalise(self) -> OtpVerifyRequest:
        try:
            object.__setattr__(self, "phone", normalise_nigerian_phone(self.phone))
        except InvalidPhoneError as exc:
            raise ValueError(str(exc)) from exc
        return self


class UserPublic(BaseModel):
    id: UUID
    # AccountRole (not Role): this reflects the account's real role back to the
    # caller, so admin / legal_team / bank_partner logins must validate here.
    role: AccountRole
    verified_status: str


class OtpVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_in: int
    user: UserPublic


class EmailVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # The high-entropy token from the emailed link. POSTed (not a GET query) so
    # it never lands in server access logs or browser history.
    token: str = Field(min_length=1, max_length=512)
    purpose: EmailVerifyPurpose = "registration"


class EmailVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_in: int
    user: UserPublic


class EmailResendRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Public endpoint (the caller isn't verified/logged in yet). Only the email
    # is needed to re-send the verification link; it's normalised the same way
    # registration normalises it.
    email: str = Field(max_length=254)

    @model_validator(mode="after")
    def _normalise(self) -> EmailResendRequest:
        try:
            object.__setattr__(self, "email", normalise_email(self.email))
        except InvalidEmailError as exc:
            raise ValueError(str(exc)) from exc
        return self


class EmailResendResponse(BaseModel):
    # Deliberately generic — the response is identical whether or not the address
    # has an unverified account, so it can't be used to enumerate accounts.
    message: str = "If that email needs verification, we've sent a new link."


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_in: int
    user: UserPublic


class SetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Composition (uppercase + digit) is enforced in SetPasswordService so the
    # error maps to the standard envelope; the length floor is declared here.
    password: str = Field(min_length=8, max_length=128)


class SetPasswordResponse(BaseModel):
    message: str


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Collected on the "Personal details" onboarding screen (SCRUM-132), after
    # OTP verification. full_name is required by the design; email is optional
    # (it is what /auth/login authenticates on, so users who skip it here can
    # add it later). Blank-after-strip full_name is rejected in ProfileService.
    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class ProfileUpdateResponse(BaseModel):
    message: str


class SellerAuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Declared on the "Seller Verification" onboarding screen (SCRUM-132). A PoA
    # holder is then routed to the PoA-document upload; an owner verifies a NIN.
    authority_type: SellerAuthorityType


class SellerAuthorityResponse(BaseModel):
    message: str
    authority_type: SellerAuthorityType


class SellerPoaStatusResponse(BaseModel):
    """A seller's own PoA verification tracking (SCRUM-137)."""

    authority_type: str | None
    status: str
    has_document: bool
    submitted_at: str | None
    rejection_reason: str | None
    can_publish: bool


# Mirrors the loan-service employment values so the two stay consistent.
EmploymentStatus = Literal["employed", "self_employed", "business_owner", "unemployed"]


class BuyerProfileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # All optional — the onboarding "Personal Information" screen has "Skip for
    # now". budget_kobo is BIGINT kobo (the naira figure ×100).
    employment_status: EmploymentStatus | None = None
    preferred_location: str | None = Field(default=None, max_length=120)
    budget_kobo: int | None = Field(default=None, ge=0)


class BuyerProfileResponse(BaseModel):
    message: str


class TokenRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    refresh_token: str = Field(min_length=1)


class TokenRefreshResponse(BaseModel):
    access_token: str
    # Rotation: a brand-new refresh token is returned each call (see
    # TokenRefreshService); the caller must replace the one it sent.
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_in: int


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    refresh_token: str = Field(min_length=1)


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"


class BvnVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Accepted as a bounded free string (no regex): format is validated in
    # the service so the 422 carries BVN_FORMAT_INVALID and the BVN value is
    # never echoed back in a Pydantic validation error.
    bvn: str = Field(min_length=1, max_length=64)


class BvnVerifyResponse(BaseModel):
    message: str = "BVN verification initiated"
    status: str = "pending"


class NinVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Bounded free string (no regex): format is validated in the service so
    # the 422 carries NIN_FORMAT_INVALID and the NIN is never echoed in a
    # Pydantic validation error.
    nin: str = Field(min_length=1, max_length=64)


class NinVerifyResponse(BaseModel):
    message: str = "NIN verification initiated"
    status: str = "pending"


class PoaUploadResponse(BaseModel):
    # The S3 key is an internal, private reference (not a URL). Returned so
    # the client can correlate the upload; the document is only ever served
    # later via a short-TTL pre-signed URL, never this key directly.
    message: str = "PoA document uploaded; awaiting verification"
    poa_verified_status: str = "pending"
    s3_key: str


class ErrorResponse(BaseModel):
    """Matches the standard error envelope in api-contracts.md."""

    error_code: str
    message: str
    trace_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)
