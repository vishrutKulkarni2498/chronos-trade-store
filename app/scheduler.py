"""Scheduled expiry job (rule R4)."""
import logging

from sqlalchemy.orm import sessionmaker

from app.clock import Clock, today_utc
from app.repository import TradeRepository
from app.services import TradeService

logger = logging.getLogger(__name__)

JOB_ID = "expire-matured-trades"


def run_expiry_job(session_factory: sessionmaker, clock: Clock = today_utc) -> int:
    with session_factory() as session:
        service = TradeService(TradeRepository(session), clock)
        count = service.expire_matured_trades()
    logger.info("Expiry job marked %d trade(s) as expired", count)
    return count


def start_scheduler(session_factory: sessionmaker, interval_minutes: int, clock: Clock = today_utc):
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_expiry_job,
        "interval",
        minutes=interval_minutes,
        args=[session_factory, clock],
        id=JOB_ID,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler