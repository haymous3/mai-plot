"""The linked-accounts claim on access tokens (SCRUM-236)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest

from app.services.jwt_verifier import JwtVerifier, TokenInvalid

SECRET = "test-secret-please-ignore-must-be-long-enough"
ISSUER = "maiplot-platform"


def _token(**extra: Any) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "sub": str(uuid4()),
        "role": "buyer",
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        **extra,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def _verifier() -> JwtVerifier:
    return JwtVerifier(secret=SECRET, issuer=ISSUER)


def test_linked_accounts_are_read_from_the_token() -> None:
    a, b = uuid4(), uuid4()
    claims = _verifier().decode_access(_token(linked_user_ids=[str(a), str(b)]))
    assert claims.linked_user_ids == frozenset({a, b})


def test_a_token_from_before_the_claim_existed_reads_as_no_links() -> None:
    assert _verifier().decode_access(_token()).linked_user_ids == frozenset()


@pytest.mark.parametrize("bad", ["not-a-list", ["not-a-uuid"], {"a": 1}])
def test_a_garbled_claim_is_rejected_not_treated_as_empty(bad: object) -> None:
    """Treating it as empty would silently switch off the own-listing guard."""
    with pytest.raises(TokenInvalid):
        _verifier().decode_access(_token(linked_user_ids=bad))
