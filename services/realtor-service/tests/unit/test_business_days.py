"""Unit tests for add_business_days (SCRUM-74)."""

from __future__ import annotations

from datetime import datetime

from app.services.business_days import add_business_days

# 2026-06-01 is a Monday; 06-05 Friday; 06-06 Saturday.
_MON = datetime(2026, 6, 1, 12, 0)
_FRI = datetime(2026, 6, 5, 12, 0)
_SAT = datetime(2026, 6, 6, 9, 0)


def test_zero_days_is_noop() -> None:
    assert add_business_days(_MON, 0) == _MON


def test_one_business_day_within_week() -> None:
    assert add_business_days(_MON, 1).date() == datetime(2026, 6, 2).date()  # Tue


def test_five_business_days_is_one_week() -> None:
    assert add_business_days(_MON, 5).date() == datetime(2026, 6, 8).date()  # next Mon


def test_skips_weekend_from_friday() -> None:
    assert add_business_days(_FRI, 1).date() == datetime(2026, 6, 8).date()  # Mon


def test_from_saturday_lands_on_weekday() -> None:
    assert add_business_days(_SAT, 1).date() == datetime(2026, 6, 8).date()  # Mon
