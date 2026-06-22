"""Platform fee calculation (SCRUM-119) — pure kobo arithmetic."""

from __future__ import annotations

import pytest

from app.services.fees import compute_platform_fee_kobo


def test_default_rate_is_two_point_five_percent() -> None:
    # ₦50,000,000 = 5,000,000,000 kobo; 2.5% = 125,000,000 kobo.
    assert compute_platform_fee_kobo(5_000_000_000, 250) == 125_000_000


def test_rate_is_configurable() -> None:
    assert compute_platform_fee_kobo(5_000_000_000, 500) == 250_000_000  # 5%
    assert compute_platform_fee_kobo(5_000_000_000, 100) == 50_000_000  # 1%


def test_fee_is_floored_never_rounded_up() -> None:
    # 1,001 kobo * 250 / 10_000 = 25.025 -> floor 25 (favours the seller).
    assert compute_platform_fee_kobo(1_001, 250) == 25


def test_zero_price_or_zero_rate_is_zero() -> None:
    assert compute_platform_fee_kobo(0, 250) == 0
    assert compute_platform_fee_kobo(5_000_000_000, 0) == 0


def test_negative_inputs_raise() -> None:
    with pytest.raises(ValueError):
        compute_platform_fee_kobo(-1, 250)
    with pytest.raises(ValueError):
        compute_platform_fee_kobo(5_000_000_000, -1)
