"""OTP code generation + bcrypt hashing.

bcrypt is the algorithm CLAUDE.md mandates for OTP and PII hashes.
`secrets.randbelow` gives a uniform draw from [0, 1_000_000) so every
6-digit code is equally likely; `str.zfill(6)` keeps the leading zeros.
"""

from __future__ import annotations

import secrets

import bcrypt

CODE_LENGTH = 6
_CODE_MAX = 10**CODE_LENGTH


def generate_code() -> str:
    """Return a uniformly-random zero-padded 6-digit code."""
    return str(secrets.randbelow(_CODE_MAX)).zfill(CODE_LENGTH)


def hash_code(code: str) -> str:
    """bcrypt-hash an OTP. Salt is generated per call (cost=12 default)."""
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_code(code: str, hashed: str) -> bool:
    """Constant-time bcrypt verification. Returns False on malformed hash."""
    try:
        return bcrypt.checkpw(code.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
