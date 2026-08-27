"""Change the caller's password, proving they know the current one — SCRUM-188.

⚠️ WHY THIS EXISTS RATHER THAN REUSING SetPasswordService. /auth/set-password
takes only {password}: it is the post-verification path, where possession of a
just-issued access token IS the proof of identity. Pointing a Settings "Change
Password" form at it would let anyone holding a live session change the password
WITHOUT knowing the current one — the exact scenario a change-password form is
supposed to defend against (a borrowed laptop, a session left open).

So this endpoint verifies the current password against the stored bcrypt hash
before writing the new one.

⚠️ IT ALSO REVOKES EVERY REFRESH TOKEN, including the caller's own. A password
change that leaves previously issued sessions alive is half a fix — the point is
to lock out whoever might already hold one. That signs the user out everywhere;
the UI tells them so and sends them to sign in again. Revoking all rather than
"all but mine" is deliberate: the access token does not identify which refresh
token issued it, so "all but mine" cannot be done correctly here, and failing
open on that would be the wrong default.

Non-§11: writes auth_credentials + refresh_tokens, never the users table. The
plaintext is bcrypt-hashed and never logged.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.services.password import hash_password, is_strong, verify_password
from app.services.set_password import WeakPassword


class NoPasswordSet(RuntimeError):
    """The account has no password yet, so there is no current one to verify.

    Reachable: password is optional at registration, so an account created
    without one has no auth_credentials row. Such a user should go through
    set-password, not change-password.
    """


class CurrentPasswordWrong(RuntimeError):
    """The supplied current password does not match the stored hash."""


class SamePassword(RuntimeError):
    """The new password equals the current one — a no-op that would otherwise
    report success and leave the user thinking they had rotated it."""


class ChangePasswordService:
    def __init__(
        self,
        *,
        credentials: AuthCredentialsRepository,
        refresh_tokens: RefreshTokenRepository,
    ) -> None:
        self._credentials = credentials
        self._refresh_tokens = refresh_tokens

    async def change(self, *, user_id: UUID, current_password: str, new_password: str) -> None:
        stored = await self._credentials.get_password_hash(user_id)
        if stored is None:
            raise NoPasswordSet
        if not verify_password(current_password, stored):
            raise CurrentPasswordWrong
        # Checked AFTER the current-password check, so a wrong guess cannot be
        # used to probe whether some candidate equals the stored password.
        if verify_password(new_password, stored):
            raise SamePassword
        if not is_strong(new_password):
            raise WeakPassword

        await self._credentials.upsert(user_id=user_id, password_hash=hash_password(new_password))
        await self._refresh_tokens.revoke_all_for_user(user_id)
