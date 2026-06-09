"""SQLAlchemy ORM models owned by auth-service.

This module is intentionally minimal — only what tests + the first
handlers need. New columns are added when a real handler reads or writes
them, not speculatively. The schema itself is owned by the alembic
migrations in services/auth-service/migrations/versions/.
"""

from app.models.auth_credential import AuthCredential
from app.models.otp_code import OtpCode
from app.models.refresh_token import RefreshToken
from app.models.user import Base, User
from app.models.user_pii import UserPii

__all__ = ["Base", "User", "UserPii", "OtpCode", "RefreshToken", "AuthCredential"]
