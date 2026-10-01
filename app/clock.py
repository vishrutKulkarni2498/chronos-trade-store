"""Injectable clock.

"Today" is always the current date in UTC (assumption A8). Services receive a
clock callable so tests can control the date without patching.
"""
from collections.abc import Callable
from datetime import date, datetime, timezone

Clock = Callable[[], date]


def today_utc() -> date:
    return datetime.now(timezone.utc).date()