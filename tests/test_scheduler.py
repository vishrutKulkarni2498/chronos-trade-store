from datetime import timedelta

from app.repository import TradeRepository
from app.scheduler import JOB_ID, run_expiry_job, start_scheduler
from app.services import TradeService


def test_run_expiry_job_marks_matured_trades(session_factory, clock, make_trade):
    with session_factory() as session:
        service = TradeService(TradeRepository(session), clock)
        service.submit_trade(make_trade(trade_id="SOON", maturity_date=clock() + timedelta(days=1)))
        service.submit_trade(make_trade(trade_id="LATER", maturity_date=clock() + timedelta(days=90)))
    clock.advance(2)

    assert run_expiry_job(session_factory, clock) == 1

    with session_factory() as session:
        repository = TradeRepository(session)
        assert repository.get("SOON", 1).expired is True
        assert repository.get("LATER", 1).expired is False


def test_start_scheduler_registers_the_expiry_job(session_factory, clock):
    scheduler = start_scheduler(session_factory, interval_minutes=5, clock=clock)
    try:
        jobs = scheduler.get_jobs()
        assert [job.id for job in jobs] == [JOB_ID]
    finally:
        scheduler.shutdown(wait=False)