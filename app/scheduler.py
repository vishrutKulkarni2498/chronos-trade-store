"""Scheduled expiry job (rule R4) and monitoring of its runs."""
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.clock import Clock, NowClock, now_utc, today_utc
from app.repository import TradeRepository
from app.services import TradeService

logger = logging.getLogger(__name__)

JOB_ID = "expire-matured-trades"


@dataclass(frozen=True)
class RunRecord:
    """The outcome of one execution of the expiry job."""

    trigger: str  # "startup" (catch-up at application start) or "schedule"
    started_at: datetime
    finished_at: datetime
    success: bool
    trades_expired: int
    error: str | None = None

    @property
    def duration_ms(self) -> int:
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


@dataclass(frozen=True)
class MonitorSnapshot:
    last_run: RunRecord | None
    runs: int
    failures: int
    trades_expired: int


class SchedulerMonitor:
    """Thread-safe, in-memory record of expiry job runs.

    The job runs on a background thread while requests read the status from
    another, hence the lock. State lives in this process only and resets when
    the application restarts.
    """

    def __init__(self, now: NowClock = now_utc) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._last_run: RunRecord | None = None
        self._runs = 0
        self._failures = 0
        self._trades_expired = 0

    def now(self) -> datetime:
        return self._now()

    def record(self, run: RunRecord) -> None:
        with self._lock:
            self._last_run = run
            self._runs += 1
            if run.success:
                self._trades_expired += run.trades_expired
            else:
                self._failures += 1

    def snapshot(self) -> MonitorSnapshot:
        with self._lock:
            return MonitorSnapshot(
                last_run=self._last_run,
                runs=self._runs,
                failures=self._failures,
                trades_expired=self._trades_expired,
            )


@dataclass(frozen=True)
class SchedulerStatus:
    enabled: bool
    running: bool
    interval_minutes: int
    job_id: str
    next_run_time: datetime | None
    last_run: RunRecord | None
    total_runs: int
    total_failures: int
    total_trades_expired: int


def run_expiry_job(
    session_factory: sessionmaker,
    clock: Clock = today_utc,
    monitor: SchedulerMonitor | None = None,
    trigger: str = "schedule",
) -> int:
    started_at = monitor.now() if monitor is not None else None
    try:
        with session_factory() as session:
            service = TradeService(TradeRepository(session), clock)
            count = service.expire_matured_trades()
    except Exception as exc:
        logger.exception("Expiry job failed")
        if monitor is not None:
            monitor.record(
                RunRecord(
                    trigger=trigger,
                    started_at=started_at,
                    finished_at=monitor.now(),
                    success=False,
                    trades_expired=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        raise

    if monitor is not None:
        monitor.record(
            RunRecord(
                trigger=trigger,
                started_at=started_at,
                finished_at=monitor.now(),
                success=True,
                trades_expired=count,
            )
        )
    logger.info("Expiry job (%s) marked %d trade(s) as expired", trigger, count)
    return count


def start_scheduler(
    session_factory: sessionmaker,
    interval_minutes: int,
    clock: Clock = today_utc,
    monitor: SchedulerMonitor | None = None,
):
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_expiry_job,
        "interval",
        minutes=interval_minutes,
        args=[session_factory, clock, monitor],
        id=JOB_ID,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


def get_status(
    scheduler: Any | None,
    monitor: SchedulerMonitor,
    *,
    enabled: bool,
    interval_minutes: int,
) -> SchedulerStatus:
    """Combine live scheduler state with the recorded run history."""
    running = False
    next_run_time = None
    if scheduler is not None:
        running = bool(scheduler.running)
        job = scheduler.get_job(JOB_ID)
        raw_next = getattr(job, "next_run_time", None) if job is not None else None
        if raw_next is not None:
            next_run_time = raw_next.astimezone(timezone.utc)

    snapshot = monitor.snapshot()
    return SchedulerStatus(
        enabled=enabled,
        running=running,
        interval_minutes=interval_minutes,
        job_id=JOB_ID,
        next_run_time=next_run_time,
        last_run=snapshot.last_run,
        total_runs=snapshot.runs,
        total_failures=snapshot.failures,
        total_trades_expired=snapshot.trades_expired,
    )