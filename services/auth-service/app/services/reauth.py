"""Step-up re-authentication — "confirm it's you" (SCRUM-223).

A signed-in session is not, on its own, enough authority to redirect money.
Changing where payouts go is exactly what someone holding a stolen session
would do, so that action asks for the password again first.

This service checks the password and answers with a SHORT-LIVED reauth token:
a JWT of `type: "reauth"`, bound to the account (`sub`) that asked, valid for
`reauth_token_minutes`. The service performing the sensitive action verifies it
with the shared JWT secret — no call back here, the same way access tokens
already work across services.

The password is the LOGIN's (SCRUM-236): a seller account that shares a buyer's
sign-in confirms with the owner's password, but the token names the seller
account, because that is the account whose payout details are changing.

⚠️ This endpoint is a password oracle for whoever holds a session, so it is
rate limited per account. The limiter fails open on a Redis outage (review.md
R5), as every limiter here does; bcrypt's cost still bounds guessing speed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import bcrypt

from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.user_repo import UserRepository
from app.services.jwt_service import JwtService
from app.services.password import verify_password
from app.services.rate_limit import OtpRateLimiter
from app.services.shared_login import login_scope

logger = logging.getLogger(__name__)

# Keeps a missing-credential answer as slow as a wrong-password one.
_DUMMY_HASH = bcrypt.hashpw(b"reauth-timing-equaliser", bcrypt.gensalt()).decode("utf-8")

REAUTH_RATE_LIMIT_PREFIX = "reauth:rl:"


class ReauthError(RuntimeError):
    pass


class ReauthFailed(ReauthError):
    """Wrong password, or the login has no password at all."""


class ReauthRateLimited(ReauthError):
    pass


@dataclass(frozen=True)
class ReauthResult:
    token: str
    expires_in: int


class ReauthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: AuthCredentialsRepository,
        rate_limiter: OtpRateLimiter,
        jwt: JwtService,
        token_minutes: int,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._rate_limiter = rate_limiter
        self._jwt = jwt
        self._token_minutes = token_minutes

    async def confirm(self, *, user_id: UUID, password: str) -> ReauthResult:
        limit = await self._rate_limiter.check_and_record(str(user_id))
        if not limit.allowed:
            raise ReauthRateLimited()

        owner_id, _ = await login_scope(self._users, user_id)
        stored = await self._credentials.get_password_hash(owner_id)
        if stored is None:
            verify_password(password, _DUMMY_HASH)
            raise ReauthFailed()
        if not verify_password(password, stored):
            logger.info("reauth.failed", extra={"user_id": str(user_id)})
            raise ReauthFailed()

        token = self._jwt.issue_reauth(user_id=user_id, minutes=self._token_minutes)
        logger.info("reauth.ok", extra={"user_id": str(user_id)})
        return ReauthResult(token=token, expires_in=self._token_minutes * 60)
