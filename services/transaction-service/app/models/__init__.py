"""SQLAlchemy ORM models owned by transaction-service."""

from app.models.transaction import Base, Transaction

__all__ = ["Base", "Transaction"]
