"""SQLAlchemy ORM models owned by auth-service.

This module is intentionally minimal — only what tests + the first
handlers need. New columns are added when a real handler reads or writes
them, not speculatively. The schema itself is owned by the alembic
migrations in services/auth-service/migrations/versions/.
"""

from app.models.audit_log import AuditLog
from app.models.auth_credential import AuthCredential
from app.models.buyer_profile import BuyerProfile
from app.models.email_verification_token import EmailVerificationToken
from app.models.otp_code import OtpCode
from app.models.realtor_registration_number import RealtorRegistrationNumber
from app.models.refresh_token import RefreshToken
from app.models.user import Base, User
from app.models.user_pii import UserPii

__all__ = [
    "Base",
    "User",
    "UserPii",
    "OtpCode",
    "EmailVerificationToken",
    "RefreshToken",
    "AuthCredential",
    "RealtorRegistrationNumber",
    "AuditLog",
    "BuyerProfile",
]
