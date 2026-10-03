from datetime import date, datetime, timedelta, timezone

from freezegun import freeze_time

from app.clock import IST, now_utc, to_ist, today_utc


@freeze_time("2026-09-30 23:59:59")
def test_today_utc_returns_current_utc_date():
    assert today_utc() == date(2026, 9, 30)


@freeze_time("2026-10-01 00:00:00")
def test_today_utc_rolls_over_at_midnight_utc():
    assert today_utc() == date(2026, 10, 1)


@freeze_time("2026-09-30 12:34:56")
def test_now_utc_returns_timezone_aware_utc_datetime():
    moment = now_utc()
    assert moment == datetime(2026, 9, 30, 12, 34, 56, tzinfo=timezone.utc)
    assert moment.utcoffset().total_seconds() == 0


def test_ist_is_utc_plus_5_30():
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


def test_to_ist_keeps_the_same_instant():
    utc = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    ist = to_ist(utc)

    assert ist == utc  # same moment in time
    assert (ist.hour, ist.minute) == (17, 30)
    assert ist.utcoffset() == timedelta(hours=5, minutes=30)


def test_to_ist_can_move_to_the_next_calendar_day():
    utc = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)

    ist = to_ist(utc)

    assert (ist.year, ist.month, ist.day, ist.hour, ist.minute) == (2026, 10, 1, 1, 30)