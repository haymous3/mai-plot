"""JWT issuance + refresh-token hashing.

The access token carries the fields Kong expects (iss claim drives Kong's
key_claim_name lookup) plus user_id and role for service-layer RBAC. The
refresh token is signed too so callers can verify before the DB lookup,
and stored as a sha256 hash in refresh_tokens.token_hash — bcrypt is
overkill here and too slow for the refresh path.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

ALGORITHM = "HS256"


class JwtError(RuntimeError):
    """Base for token decode failures."""


class TokenExpired(JwtError):
    pass


class TokenInvalid(JwtError):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_token_hash: str
    access_expires_in: int
    refresh_expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    """The subset of verified claims callers act on."""

    user_id: UUID
    token_type: str
    role: str | None
    jti: str | None


class JwtService:
    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        access_expire_minutes: int,
        refresh_expire_days: int,
    ) -> None:
        self._secret = secret
        self._issuer = issuer
        self._access_expire_minutes = access_expire_minutes
        self._refresh_expire_days = refresh_expire_days

    def issue_pair(self, *, user_id: UUID, role: str) -> TokenPair:
        now = datetime.now(UTC)
        access_exp = now + timedelta(minutes=self._access_expire_minutes)
        refresh_exp = now + timedelta(days=self._refresh_expire_days)

        access_payload: dict[str, Any] = {
            "iss": self._issuer,
            "sub": str(user_id),
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int(access_exp.timestamp()),
            "type": "access",
        }
        access_token = jwt.encode(access_payload, self._secret, algorithm=ALGORITHM)

        # Refresh token includes a random jti so each issuance is unique
        # even if user_id + role + timestamp collide. The DB stores the
        # hash; the token itself is signed so we can short-circuit on a
        # bad signature without a DB round trip.
        jti = secrets.token_urlsafe(16)
        refresh_payload: dict[str, Any] = {
            "iss": self._issuer,
            "sub": str(user_id),
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(refresh_exp.timestamp()),
            "type": "refresh",
        }
        refresh_token = jwt.encode(refresh_payload, self._secret, algorithm=ALGORITHM)
        refresh_hash = _sha256(refresh_token)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            refresh_token_hash=refresh_hash,
            access_expires_in=self._access_expire_minutes * 60,
            refresh_expires_at=refresh_exp,
        )

    def decode(self, token: str, *, expected_type: str) -> TokenClaims:
        """Verify signature + expiry + issuer and return the claims.

        Raises TokenExpired if the exp has passed, TokenInvalid for a bad
        signature, wrong issuer, malformed token, or a token whose `type`
        claim is not `expected_type` (so an access token can't be replayed
        on the refresh path, or vice versa).
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                issuer=self._issuer,
                options={"require": ["exp", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpired() from exc
        except jwt.InvalidTokenError as exc:
            raise TokenInvalid() from exc

        if payload.get("type") != expected_type:
            raise TokenInvalid()

        try:
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise TokenInvalid() from exc

        return TokenClaims(
            user_id=user_id,
            token_type=expected_type,
            role=payload.get("role"),
            jti=payload.get("jti"),
        )

    @staticmethod
    def hash_token(token: str) -> str:
        """sha256 hex of a refresh token — matches the stored token_hash."""
        return _sha256(token)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
