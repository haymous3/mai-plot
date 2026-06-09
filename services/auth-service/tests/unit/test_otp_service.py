"""OTP code generation, hashing, and verification."""

from __future__ import annotations

import re

from app.services.otp import generate_code, hash_code, verify_code

_DIGIT_RE = re.compile(r"^\d{6}$")


def test_generate_code_is_six_digits() -> None:
    for _ in range(50):
        code = generate_code()
        assert _DIGIT_RE.match(code), code


def test_generate_code_includes_leading_zeros() -> None:
    # Across many draws we should occasionally see at least one code
    # starting with '0'. Probability of not seeing one in 200 draws is
    # 0.9^200 ≈ 7e-10; flakiness here would indicate a real bug.
    codes = [generate_code() for _ in range(200)]
    assert any(c.startswith("0") for c in codes)


def test_verify_code_round_trip() -> None:
    code = "482910"
    hashed = hash_code(code)
    assert verify_code(code, hashed) is True
    assert verify_code("000000", hashed) is False


def test_verify_code_handles_bad_hash() -> None:
    assert verify_code("482910", "not-a-bcrypt-hash") is False
    assert verify_code("482910", "") is False
