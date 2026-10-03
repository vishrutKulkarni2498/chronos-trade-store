"""Injectable clocks.

"Today" is always the current date in UTC (assumption A8). Services receive a
clock callable so tests can control the date without patching. A second clock
supplies full timestamps, used to record when scheduled jobs ran.
"""
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

Clock = Callable[[], date]
NowClock = Callable[[], datetime]


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Indian Standard Time: UTC+05:30 all year (India has no daylight saving). A fixed
# offset avoids depending on a system time zone database, which Windows lacks by default.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def to_ist(moment: datetime) -> datetime:
    """Express a moment in IST. For display only: everything is stored and computed in UTC."""
    return moment.astimezone(IST)