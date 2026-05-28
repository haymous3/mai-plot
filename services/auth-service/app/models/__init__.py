"""SQLAlchemy ORM models owned by auth-service.

This module is intentionally minimal — only what tests + the first
handlers need. New columns are added when a real handler reads or writes
them, not speculatively. The schema itself is owned by the alembic
migrations in services/auth-service/migrations/versions/.
"""

from app.models.user import Base, User

__all__ = ["Base", "User"]
