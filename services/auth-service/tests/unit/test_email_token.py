"""Magic-link token generation + hashing (SCRUM-152)."""

from __future__ import annotations

import hashlib

from app.services.email_token import generate_token, hash_token


def test_generate_token_is_urlsafe_and_unique() -> None:
    tokens = {generate_token() for _ in range(100)}
    # 256 bits of entropy → no collisions across a small sample.
    assert len(tokens) == 100
    for token in tokens:
        # token_urlsafe uses only URL-safe base64 alphabet (no '=' padding).
        assert all(c.isalnum() or c in "-_" for c in token)
        assert len(token) >= 40  # ~43 chars for 32 bytes


def test_hash_token_is_sha256_hex() -> None:
    token = "some-token-value"
    digest = hash_token(token)
    assert digest == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_token_is_deterministic() -> None:
    token = generate_token()
    assert hash_token(token) == hash_token(token)
