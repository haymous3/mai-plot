"""Business-day arithmetic for commission availability (SCRUM-74).

A commission becomes available N business days after the deal closes (weekends
skipped). Public holidays are out of scope for now.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def add_business_days(start: datetime, days: int) -> datetime:
    """`start` advanced by `days` weekdays (Mon-Fri). days<=0 returns start."""
    result = start
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:  # 0=Mon .. 4=Fri
            added += 1
    return result
