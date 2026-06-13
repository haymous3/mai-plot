"""Access-token verification (decode-only).

document-service consumes access tokens minted by auth-service; it never
issues them. Verifies HS256 signature, issuer, expiry, and type=access using
the shared secret, returning user_id + role.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt

ALGORITHM = "HS256"


class JwtError(RuntimeError):
    pass


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
