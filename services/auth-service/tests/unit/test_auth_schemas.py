"""Schema-level guards for the auth role Literals (SCRUM-151).

The registration role and the response role are intentionally different sets:
public registration may only mint seller/buyer/realtor, but a login response
must faithfully reflect ANY role the account actually holds — including the
out-of-band admin/legal_team/bank_partner roles the DB allows. Conflating the
two made admin login 500 on the response schema.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest, UserPublic

# Mirrors the DB users_role_check constraint exactly.
_DB_ROLES = ("seller", "buyer", "realtor", "bank_partner", "admin", "legal_team")


@pytest.mark.parametrize("role", _DB_ROLES)
def test_user_public_accepts_every_db_role(role: str) -> None:
    # This is the regression: role="admin"/"legal_team" previously raised a
    # literal_error here, which the login route surfaced as HTTP 500.
    user = UserPublic.model_validate(
        {"id": uuid4(), "role": role, "verified_status": "phone_verified"}
    )
    assert user.role == role


def test_user_public_rejects_unknown_role() -> None:
    # The contract is still closed — an unexpected role is a 500, not silently
    # accepted (preserves the "surface, don't widen" behaviour of the route).
    with pytest.raises(ValidationError):
        UserPublic.model_validate(
            {"id": uuid4(), "role": "super_admin", "verified_status": "phone_verified"}
        )


@pytest.mark.parametrize("role", ("admin", "legal_team", "bank_partner"))
def test_register_request_rejects_privileged_roles(role: str) -> None:
    # RBAC: public self-registration must NOT be able to create a privileged
    # account, even though the response schema now reflects those roles back.
    # role is a str here on purpose — that is exactly the invalid input under
    # test, so the static Literal mismatch is expected.
    with pytest.raises(ValidationError):
        RegisterRequest(phone="08012345678", role=role, email="x@example.com")  # type: ignore[arg-type]


@pytest.mark.parametrize("role", ("seller", "buyer", "realtor"))
def test_register_request_accepts_public_roles(role: str) -> None:
    req = RegisterRequest(phone="08012345678", role=role, email="x@example.com")  # type: ignore[arg-type]
    assert req.role == role
