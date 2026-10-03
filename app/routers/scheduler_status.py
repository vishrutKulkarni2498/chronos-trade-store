"""Section: scheduler."""
from datetime import datetime

from fastapi import APIRouter, Request

from app.clock import to_ist
from app.routers.tags import SCHEDULER
from app.scheduler import SchedulerStatus, get_status
from app.schemas import RunRecordOut, SchedulerStatusOut, SchedulerTotals

router = APIRouter(tags=[SCHEDULER])


def _to_status_out(status: SchedulerStatus, current_time: datetime) -> SchedulerStatusOut:
    """Build the response. IST values are added here, for display only: the rest of
    the application works in UTC."""
    last = status.last_run
    next_run = status.next_run_time
    return SchedulerStatusOut(
        enabled=status.enabled,
        running=status.running,
        interval_minutes=status.interval_minutes,
        job_id=status.job_id,
        current_time_utc=current_time,
        current_time_ist=to_ist(current_time),
        next_run_time=next_run,
        next_run_time_ist=None if next_run is None else to_ist(next_run),
        last_run=None
        if last is None
        else RunRecordOut(
            trigger=last.trigger,
            started_at=last.started_at,
            started_at_ist=to_ist(last.started_at),
            finished_at=last.finished_at,
            finished_at_ist=to_ist(last.finished_at),
            duration_ms=last.duration_ms,
            success=last.success,
            trades_expired=last.trades_expired,
            error=last.error,
        ),
        totals=SchedulerTotals(
            runs=status.total_runs,
            failures=status.total_failures,
            trades_expired=status.total_trades_expired,
        ),
    )


@router.get("/scheduler/status", response_model=SchedulerStatusOut)
def scheduler_status(request: Request):
    """Whether the expiry job is enabled and running, when it runs next, and how past
    runs went. Times are given in UTC, with an IST (UTC+05:30) equivalent beside each
    (`*_ist`). Run history is in memory and resets on restart."""
    state = request.app.state
    status = get_status(
        state.scheduler,
        state.monitor,
        enabled=state.scheduler_enabled,
        interval_minutes=state.interval_minutes,
    )
    return _to_status_out(status, state.monitor.now())