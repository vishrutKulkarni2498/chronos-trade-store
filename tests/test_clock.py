from datetime import date

from freezegun import freeze_time

from app.clock import today_utc


@freeze_time("2026-09-30 23:59:59")
def test_today_utc_returns_current_utc_date():
    assert today_utc() == date(2026, 9, 30)


@freeze_time("2026-10-01 00:00:00")
def test_today_utc_rolls_over_at_midnight_utc():
    assert today_utc() == date(2026, 10, 1)