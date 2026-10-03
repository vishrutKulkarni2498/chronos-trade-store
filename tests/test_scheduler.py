from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.repository import TradeRepository
from app.scheduler import (
    JOB_ID,
    RunRecord,
    SchedulerMonitor,
    get_status,
    run_expiry_job,
    start_scheduler,
)
from app.services import TradeService

T0 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def make_now(*moments):
    """A 'now' callable that returns the given moments in order."""
    iterator = iter(moments)
    return lambda: next(iterator)


def fake_scheduler(running=True, next_run=None, has_job=True):
    job = SimpleNamespace(next_run_time=next_run) if has_job else None
    return SimpleNamespace(running=running, get_job=lambda job_id: job)


def seed(session_factory, clock, make_trade, **trades):
    """Store trades by name -> days until maturity."""
    with session_factory() as session:
        service = TradeService(TradeRepository(session), clock)
        for trade_id, days in trades.items():
            service.submit_trade(
                make_trade(trade_id=trade_id, maturity_date=clock() + timedelta(days=days))
            )


# ---- the job itself ----------------------------------------------------------------
def test_run_expiry_job_marks_matured_trades(session_factory, clock, make_trade):
    seed(session_factory, clock, make_trade, SOON=1, LATER=90)
    clock.advance(2)

    assert run_expiry_job(session_factory, clock) == 1

    with session_factory() as session:
        repository = TradeRepository(session)
        assert repository.get("SOON", 1).expired is True
        assert repository.get("LATER", 1).expired is False


# ---- scheduler wiring ----------------------------------------------------------------
def test_start_scheduler_registers_the_expiry_job(session_factory, clock):
    scheduler = start_scheduler(session_factory, interval_minutes=5, clock=clock)
    try:
        assert [job.id for job in scheduler.get_jobs()] == [JOB_ID]
    finally:
        scheduler.shutdown(wait=False)


def test_scheduled_job_uses_the_configured_interval(session_factory, clock):
    scheduler = start_scheduler(session_factory, interval_minutes=5, clock=clock)
    try:
        assert scheduler.get_job(JOB_ID).trigger.interval == timedelta(minutes=5)
    finally:
        scheduler.shutdown(wait=False)


def test_registered_job_is_wired_to_the_expiry_function(session_factory, clock, make_trade):
    seed(session_factory, clock, make_trade, SOON=1)
    clock.advance(2)

    scheduler = start_scheduler(session_factory, interval_minutes=5, clock=clock)
    try:
        job = scheduler.get_job(JOB_ID)
        assert job.func(*job.args) == 1  # run exactly what the scheduler would run
    finally:
        scheduler.shutdown(wait=False)


# ---- monitoring: recording runs ------------------------------------------------------------
def test_monitor_starts_empty():
    snapshot = SchedulerMonitor().snapshot()

    assert snapshot.last_run is None
    assert (snapshot.runs, snapshot.failures, snapshot.trades_expired) == (0, 0, 0)


def test_successful_run_is_recorded(session_factory, clock, make_trade):
    seed(session_factory, clock, make_trade, SOON=1)
    clock.advance(2)
    monitor = SchedulerMonitor(make_now(T0, T0 + timedelta(milliseconds=250)))

    assert run_expiry_job(session_factory, clock, monitor, trigger="startup") == 1

    last = monitor.snapshot().last_run
    assert last.trigger == "startup"
    assert last.success is True
    assert last.trades_expired == 1
    assert last.started_at == T0
    assert last.finished_at == T0 + timedelta(milliseconds=250)
    assert last.duration_ms == 250
    assert last.error is None


def test_trigger_defaults_to_schedule(session_factory, clock):
    monitor = SchedulerMonitor()
    run_expiry_job(session_factory, clock, monitor)
    assert monitor.snapshot().last_run.trigger == "schedule"


def test_failed_run_is_recorded_and_the_error_is_reraised(clock):
    def broken_session_factory():
        raise RuntimeError("db down")

    monitor = SchedulerMonitor(make_now(T0, T0 + timedelta(seconds=1)))

    with pytest.raises(RuntimeError):
        run_expiry_job(broken_session_factory, clock, monitor)

    snapshot = monitor.snapshot()
    assert snapshot.last_run.success is False
    assert "db down" in snapshot.last_run.error
    assert snapshot.last_run.trades_expired == 0
    assert (snapshot.runs, snapshot.failures) == (1, 1)


def test_totals_accumulate_across_runs(session_factory, clock, make_trade):
    seed(session_factory, clock, make_trade, A=1, B=3)
    monitor = SchedulerMonitor()

    clock.advance(2)
    run_expiry_job(session_factory, clock, monitor)  # expires A
    clock.advance(2)
    run_expiry_job(session_factory, clock, monitor)  # expires B
    run_expiry_job(session_factory, clock, monitor)  # nothing left

    snapshot = monitor.snapshot()
    assert snapshot.runs == 3
    assert snapshot.failures == 0
    assert snapshot.trades_expired == 2
    assert snapshot.last_run.trades_expired == 0


# ---- monitoring: building the status ---------------------------------------------------------
def test_status_when_no_scheduler_exists():
    status = get_status(None, SchedulerMonitor(), enabled=False, interval_minutes=60)

    assert status.enabled is False
    assert status.running is False
    assert status.next_run_time is None
    assert status.last_run is None
    assert status.interval_minutes == 60
    assert status.job_id == JOB_ID


def test_status_reports_next_run_converted_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    next_run = datetime(2026, 9, 30, 18, 0, tzinfo=ist)

    status = get_status(
        fake_scheduler(next_run=next_run), SchedulerMonitor(), enabled=True, interval_minutes=60
    )

    assert status.running is True
    assert status.next_run_time == datetime(2026, 9, 30, 12, 30, tzinfo=timezone.utc)
    assert status.next_run_time.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "scheduler",
    [fake_scheduler(has_job=False), fake_scheduler(next_run=None)],
    ids=["job missing", "job paused"],
)
def test_status_has_no_next_run_when_job_is_missing_or_paused(scheduler):
    status = get_status(scheduler, SchedulerMonitor(), enabled=True, interval_minutes=60)
    assert status.next_run_time is None


def test_status_includes_last_run_and_totals():
    monitor = SchedulerMonitor()
    monitor.record(RunRecord("startup", T0, T0 + timedelta(seconds=1), True, 3))
    monitor.record(RunRecord("schedule", T0, T0 + timedelta(seconds=2), False, 0, "boom"))

    status = get_status(fake_scheduler(), monitor, enabled=True, interval_minutes=60)

    assert status.last_run.trigger == "schedule"
    assert status.last_run.error == "boom"
    assert status.total_runs == 2
    assert status.total_failures == 1
    assert status.total_trades_expired == 3


def test_real_scheduler_reports_a_future_next_run_then_stops(session_factory, clock):
    monitor = SchedulerMonitor()
    scheduler = start_scheduler(session_factory, 5, clock, monitor)
    try:
        status = get_status(scheduler, monitor, enabled=True, interval_minutes=5)
        now = datetime.now(timezone.utc)
        assert status.running is True
        assert now < status.next_run_time <= now + timedelta(minutes=5, seconds=5)
    finally:
        scheduler.shutdown(wait=False)

    assert get_status(scheduler, monitor, enabled=True, interval_minutes=5).running is False