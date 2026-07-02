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

from app.validators.phone import InvalidPhoneError, normalise_nigerian_phone

Role = Literal["seller", "buyer", "realtor"]
SellerAuthorityType = Literal["owner", "power_of_attorney"]
OtpPurpose = Literal["registration", "login"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phone: str
    role: Role
    # email is accepted as a free string for now; proper email validation
    # comes with /auth/login when the schema actually stores it.
    email: str | None = Field(default=None, max_length=254)
    # password is accepted for forward compatibility with /auth/login but
    # silently discarded — there is no password column on users yet.
    password: str | None = Field(default=None, min_length=8, max_length=128)
    seller_authority_type: SellerAuthorityType | None = None

    @model_validator(mode="after")
    def _normalise_and_check_seller(self) -> RegisterRequest:
        try:
            object.__setattr__(self, "phone", normalise_nigerian_phone(self.phone))
        except InvalidPhoneError as exc:
            raise ValueError(str(exc)) from exc

        if self.role == "seller" and self.seller_authority_type is None:
            raise ValueError("seller_authority_type is required when role=seller")
        if self.role != "seller" and self.seller_authority_type is not None:
            raise ValueError("seller_authority_type is only allowed when role=seller")
        return self


class RegisterResponse(BaseModel):
    user_id: UUID
    message: str
    otp_expires_in_seconds: int


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
    role: Role
    verified_status: str


class OtpVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_in: int
    user: UserPublic


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
