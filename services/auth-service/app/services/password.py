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


def is_strong(password: str) -> bool:
    """The composition policy the UI advertises: >=8 chars, an uppercase letter
    and a digit. Lives here beside hash/verify because both set-password and
    change-password enforce it (SCRUM-188) — it was previously a private helper
    in set_password.py, which the second caller would have had to reach into.
    """
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.isdigit() for c in password)
    )
