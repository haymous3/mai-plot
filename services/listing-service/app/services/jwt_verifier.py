"""Access-token verification (decode-only).

listing-service consumes access tokens minted by auth-service; it never
issues them. This verifies the HS256 signature, issuer, and expiry using the
shared secret, enforces type=access, and returns the user_id + role for
RBAC. Mirrors the decode half of auth-service's JwtService so a token valid
there is valid here.
"""

from __future__ import annotations

from dataclasses import dataclass
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
class TokenClaims:
    user_id: UUID
    role: str | None


class JwtVerifier:
    def __init__(self, *, secret: str, issuer: str) -> None:
        self._secret = secret
        self._issuer = issuer

    def decode_access(self, token: str) -> TokenClaims:
        """Verify signature + expiry + issuer and return the access claims.

        Raises TokenExpired if exp has passed, TokenInvalid for a bad
        signature, wrong issuer, malformed token, or a non-access token.
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

        if payload.get("type") != "access":
            raise TokenInvalid()

        try:
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise TokenInvalid() from exc

        return TokenClaims(user_id=user_id, role=payload.get("role"))
