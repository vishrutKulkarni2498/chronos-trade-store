"""Application wiring: builds the app, starts the scheduler, mounts the routers.

Sections of create_app:
  1. Configuration      4. Application
  2. Persistence        5. Error handling
  3. Lifecycle          6. Routers and system endpoints

Endpoint code lives in app/routers/, one module per section of the API.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import config
from app.clock import Clock, NowClock, now_utc, today_utc
from app.database import make_engine
from app.errors import register_exception_handlers
from app.models import Base
from app.routers import read_trades, scheduler_status, submit_trades
from app.routers.tags import OPENAPI_TAGS, SYSTEM
from app.scheduler import SchedulerMonitor, run_expiry_job, start_scheduler


def create_app(
    database_url: str | None = None,
    clock: Clock = today_utc,
    enable_scheduler: bool | None = None,
    now: NowClock = now_utc,
) -> FastAPI:
    # ---- 1. Configuration -------------------------------------------------------
    url = database_url or config.database_url()
    scheduler_on = config.scheduler_enabled() if enable_scheduler is None else enable_scheduler
    interval_minutes = config.expiry_interval_minutes()
    monitor = SchedulerMonitor(now)

    # ---- 2. Persistence ---------------------------------------------------------
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # ---- 3. Lifecycle: expiry scheduler -----------------------------------------
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        scheduler = None
        if scheduler_on:
            try:
                # Catch up once at startup. A failure is logged and recorded by the
                # job itself, and must not stop the API from starting.
                run_expiry_job(session_factory, clock, monitor, trigger="startup")
            except Exception:
                pass
            scheduler = start_scheduler(session_factory, interval_minutes, clock, monitor)
            _app.state.scheduler = scheduler
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
                _app.state.scheduler = None

    # ---- 4. Application ---------------------------------------------------------
    app = FastAPI(
        title="Trade Store",
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    # Shared with the routers through app.state (see app/dependencies.py).
    app.state.session_factory = session_factory
    app.state.clock = clock
    app.state.monitor = monitor
    app.state.scheduler_enabled = scheduler_on
    app.state.interval_minutes = interval_minutes
    app.state.scheduler = None

    # ---- 5. Error handling ------------------------------------------------------
    register_exception_handlers(app)

    # ---- 6. Routers and system endpoints ----------------------------------------
    app.include_router(submit_trades.router)
    app.include_router(read_trades.router)
    app.include_router(scheduler_status.router)

    @app.get("/health", tags=[SYSTEM])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()