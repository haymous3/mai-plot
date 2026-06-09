"""Password hashing — bcrypt, per CLAUDE.md.

Mirrors services/otp.py. Note bcrypt only considers the first 72 bytes of
the input; RegisterRequest caps passwords at 128 chars, so very long
passwords are effectively truncated at 72 bytes. That matches standard
bcrypt behaviour and is acceptable given the 8-char minimum.
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """bcrypt-hash a plaintext password (per-call salt, cost=12 default)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time bcrypt check. Returns False on a malformed hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
