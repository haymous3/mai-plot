"""Set/replace the caller's password after phone-OTP verification (SCRUM-94).

The onboarding wizard collects the password AFTER OTP verification (register →
verify → password), but register only stores a password if one is supplied at
registration time. This lets a just-verified user set their password using the
access token issued by /auth/otp/verify. Non-§11: writes auth_credentials (a
separate table), never the users table; the plaintext is bcrypt-hashed and never
logged.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.user_repo import UserRepository
from app.services.password import hash_password, is_strong
from app.services.shared_login import login_scope


class WeakPassword(RuntimeError):
    """The password fails the composition policy (length/uppercase/digit)."""


class SetPasswordService:
    def __init__(self, *, users: UserRepository, credentials: AuthCredentialsRepository) -> None:
        self._users = users
        self._credentials = credentials

    async def set(self, *, user_id: UUID, password: str) -> None:
        """Hash + upsert the caller's password. Enforces the same policy the UI
        shows (≥8 chars, an uppercase letter, and a number)."""
        if not is_strong(password):
            raise WeakPassword
        # Written to the LOGIN OWNER (SCRUM-236). A sharer's own credentials
        # row is never read — login resolves email to the owner — so writing
        # there would "succeed" and change nothing the person can sign in with.
        owner_id, _ = await login_scope(self._users, user_id)
        await self._credentials.upsert(user_id=owner_id, password_hash=hash_password(password))
