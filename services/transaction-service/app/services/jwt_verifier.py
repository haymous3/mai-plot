"""Access-token verification (decode-only).

transaction-service consumes access tokens minted by auth-service; it never
issues them. Verifies the HS256 signature, issuer, and expiry, enforces
type=access, and returns the user_id + role for authorization. Mirrors the
decode half of auth-service's JwtService.
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
    # The caller's OTHER accounts — same person, different row (SCRUM-236):
    # their buyer/seller account on the same sign-in and any account sharing
    # their NIN. Empty for a token minted before the claim existed.
    linked_user_ids: frozenset[UUID] = frozenset()


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

        return TokenClaims(
            user_id=user_id,
            role=payload.get("role"),
            linked_user_ids=_parse_linked(payload.get("linked_user_ids")),
        )


def _parse_linked(raw: object) -> frozenset[UUID]:
    """The linked-account claim, or TokenInvalid if it is present but garbled.

    Rejecting rather than dropping a bad value matters: this claim feeds a
    guard, and "unparseable, so treat as empty" would quietly switch it off.
    Absence is fine — tokens from before SCRUM-236 do not carry it.
    """
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise TokenInvalid()
    try:
        return frozenset(UUID(str(item)) for item in raw)
    except ValueError as exc:
        raise TokenInvalid() from exc
