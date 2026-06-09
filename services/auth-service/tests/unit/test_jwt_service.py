"""JWT issuance — payload shape, signature, expiry."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pytest

from app.services.jwt_service import JwtService

# Must be ≥32 bytes to avoid PyJWT's InsecureKeyLengthWarning (RFC 7518 §3.2).
SECRET = "test-secret-please-ignore-must-be-long-enough"
ISSUER = "maiplot-platform"


@pytest.fixture
def service() -> JwtService:
    return JwtService(
        secret=SECRET,
        issuer=ISSUER,
        access_expire_minutes=15,
        refresh_expire_days=7,
    )


def test_access_token_payload_matches_kong_expectations(service: JwtService) -> None:
    user_id = uuid4()
    tokens = service.issue_pair(user_id=user_id, role="buyer")

    payload = jwt.decode(tokens.access_token, SECRET, algorithms=["HS256"])
    assert payload["iss"] == ISSUER
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "buyer"
    assert payload["type"] == "access"
    assert payload["exp"] > payload["iat"]


def test_refresh_token_payload_and_hash(service: JwtService) -> None:
    user_id = uuid4()
    tokens = service.issue_pair(user_id=user_id, role="seller")

    payload = jwt.decode(tokens.refresh_token, SECRET, algorithms=["HS256"])
    assert payload["type"] == "refresh"
    assert payload["sub"] == str(user_id)
    # jti is random per call — distinct from any other token issued.
    assert payload["jti"]

    # The stored hash matches the issued refresh token.
    import hashlib

    expected = hashlib.sha256(tokens.refresh_token.encode("utf-8")).hexdigest()
    assert tokens.refresh_token_hash == expected


def test_access_expires_in_matches_setting(service: JwtService) -> None:
    tokens = service.issue_pair(user_id=uuid4(), role="buyer")
    assert tokens.access_expires_in == 15 * 60


def test_refresh_expires_at_in_future(service: JwtService) -> None:
    tokens = service.issue_pair(user_id=uuid4(), role="buyer")
    assert tokens.refresh_expires_at > datetime.now(UTC)
