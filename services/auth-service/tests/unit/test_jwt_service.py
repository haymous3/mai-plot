"""JWT issuance — payload shape, signature, expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.services.jwt_service import JwtService, TokenExpired, TokenInvalid

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


def test_decode_access_roundtrip(service: JwtService) -> None:
    user_id = uuid4()
    tokens = service.issue_pair(user_id=user_id, role="realtor")
    claims = service.decode(tokens.access_token, expected_type="access")
    assert claims.user_id == user_id
    assert claims.role == "realtor"
    assert claims.token_type == "access"


def test_decode_refresh_roundtrip(service: JwtService) -> None:
    user_id = uuid4()
    tokens = service.issue_pair(user_id=user_id, role="seller")
    claims = service.decode(tokens.refresh_token, expected_type="refresh")
    assert claims.user_id == user_id
    assert claims.jti  # refresh tokens carry a jti


def test_decode_rejects_wrong_type(service: JwtService) -> None:
    tokens = service.issue_pair(user_id=uuid4(), role="buyer")
    # An access token presented where a refresh token is expected.
    with pytest.raises(TokenInvalid):
        service.decode(tokens.access_token, expected_type="refresh")


def test_decode_rejects_bad_signature(service: JwtService) -> None:
    other = JwtService(
        secret="a-different-secret-also-long-enough-yes",
        issuer=ISSUER,
        access_expire_minutes=15,
        refresh_expire_days=7,
    )
    tokens = other.issue_pair(user_id=uuid4(), role="buyer")
    with pytest.raises(TokenInvalid):
        service.decode(tokens.access_token, expected_type="access")


def test_decode_rejects_wrong_issuer(service: JwtService) -> None:
    foreign = JwtService(
        secret=SECRET,
        issuer="someone-else",
        access_expire_minutes=15,
        refresh_expire_days=7,
    )
    tokens = foreign.issue_pair(user_id=uuid4(), role="buyer")
    with pytest.raises(TokenInvalid):
        service.decode(tokens.access_token, expected_type="access")


def test_decode_raises_token_expired(service: JwtService) -> None:
    now = datetime.now(UTC)
    payload = {
        "iss": ISSUER,
        "sub": str(uuid4()),
        "role": "buyer",
        "iat": int((now - timedelta(minutes=30)).timestamp()),
        "exp": int((now - timedelta(minutes=15)).timestamp()),
        "type": "access",
    }
    expired = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(TokenExpired):
        service.decode(expired, expected_type="access")


def test_hash_token_matches_issued_hash(service: JwtService) -> None:
    tokens = service.issue_pair(user_id=uuid4(), role="buyer")
    assert service.hash_token(tokens.refresh_token) == tokens.refresh_token_hash
