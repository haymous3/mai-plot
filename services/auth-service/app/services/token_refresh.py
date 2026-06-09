"""Refresh-token rotation.

Per SCRUM-45 acceptance criteria the refresh token is *rotated* on every
call: the presented token is revoked and a brand-new access+refresh pair
is issued. This bounds the blast radius of a leaked refresh token to a
single use, and makes replay detectable (a revoked token presented again
returns 401 REFRESH_TOKEN_REVOKED).

Note: api-contracts.md's example shows "same refresh_token" returned —
the ticket's rotation requirement supersedes it; the contract example is
stale and is being followed up separately.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.jwt_service import (
    JwtService,
    TokenExpired,
    TokenInvalid,
    TokenPair,
)

logger = logging.getLogger(__name__)


class TokenRefreshError(RuntimeError):
    pass


class RefreshTokenInvalid(TokenRefreshError):
    pass


class RefreshTokenExpired(TokenRefreshError):
    pass


class RefreshTokenRevoked(TokenRefreshError):
    pass


@dataclass(frozen=True)
class RefreshResult:
    tokens: TokenPair
    role: str


class TokenRefreshService:
    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        jwt: JwtService,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._jwt = jwt

    async def refresh(self, *, refresh_token: str) -> RefreshResult:
        # 1. Cheap, DB-free checks first: signature, issuer, expiry, type.
        #    We don't need the claims — the DB row is the source of truth
        #    for identity; this just rejects forged/expired tokens early.
        try:
            self._jwt.decode(refresh_token, expected_type="refresh")
        except TokenExpired as exc:
            raise RefreshTokenExpired() from exc
        except TokenInvalid as exc:
            raise RefreshTokenInvalid() from exc

        # 2. The token must exist in the store and not be revoked. A valid
        #    signature is not enough — rotation means each token is usable
        #    exactly once.
        stored = await self._refresh_tokens.get_by_hash(self._jwt.hash_token(refresh_token))
        if stored is None:
            raise RefreshTokenInvalid()
        if stored.revoked_at is not None:
            raise RefreshTokenRevoked()
        if stored.expires_at <= datetime.now(UTC):
            raise RefreshTokenExpired()

        # 3. The account must still be live (covers soft-delete/deactivation
        #    happening after the token was issued).
        user = await self._users.get_active_by_id(stored.user_id)
        if user is None:
            raise RefreshTokenInvalid()

        # 4. Rotate: burn the presented token, mint a fresh pair, persist it.
        await self._refresh_tokens.revoke(stored.id)
        tokens = self._jwt.issue_pair(user_id=user.id, role=user.role)
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=tokens.refresh_token_hash,
            expires_at=tokens.refresh_expires_at,
        )

        logger.info(
            "token_refresh.ok",
            extra={"user_id": str(user.id), "role": user.role},
        )
        return RefreshResult(tokens=tokens, role=user.role)
