"""FastAPI application: HTTP concerns only. Rules live in the service layer."""
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app import config
from app.clock import Clock, today_utc
from app.database import make_engine
from app.exceptions import (
    LowerVersionError,
    PastMaturityDateError,
    TradeNotFoundError,
    TradeStoreError,
)
from app.models import Base
from app.repository import TradeRepository
from app.scheduler import run_expiry_job, start_scheduler
from app.schemas import (
    BulkItemResult,
    BulkResponse,
    BulkSummary,
    TradeCreate,
    TradeOut,
)
from app.services import TradeService


def _describe(item: Any) -> tuple[str | None, int | None]:
    """Best-effort trade_id/version from a raw bulk item, for error reporting."""
    if not isinstance(item, dict):
        return None, None
    raw_id = item.get("trade_id")
    raw_version = item.get("version")
    trade_id = str(raw_id) if raw_id is not None else None
    is_int = isinstance(raw_version, int) and not isinstance(raw_version, bool)
    return trade_id, raw_version if is_int else None


def create_app(
    database_url: str | None = None,
    clock: Clock = today_utc,
    enable_scheduler: bool | None = None,
) -> FastAPI:
    url = database_url or config.database_url()
    scheduler_on = config.scheduler_enabled() if enable_scheduler is None else enable_scheduler

    engine = make_engine(url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        scheduler = None
        if scheduler_on:
            run_expiry_job(session_factory, clock)  # catch up once at startup
            scheduler = start_scheduler(session_factory, config.expiry_interval_minutes(), clock)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    app = FastAPI(title="Trade Store", version="1.0.0", lifespan=lifespan)

    def get_service():
        session = session_factory()
        try:
            yield TradeService(TradeRepository(session), clock)
        finally:
            session.close()

    # ---- domain exception -> HTTP mapping -------------------------------------
    @app.exception_handler(LowerVersionError)
    async def lower_version_handler(_request: Request, exc: LowerVersionError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(PastMaturityDateError)
    async def past_maturity_handler(_request: Request, exc: PastMaturityDateError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(TradeNotFoundError)
    async def not_found_handler(_request: Request, exc: TradeNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # ---- routes ---------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/trades", response_model=TradeOut, status_code=201)
    def submit_trade(
        payload: TradeCreate,
        response: Response,
        service: TradeService = Depends(get_service),
    ):
        trade, created = service.submit_trade(payload)
        if not created:
            response.status_code = 200  # same version replaced the existing record
        return trade

    @app.post("/trades/bulk", response_model=BulkResponse)
    def submit_bulk(
        items: list[Any] = Body(...),
        service: TradeService = Depends(get_service),
    ):
        results: list[BulkItemResult] = []
        for index, item in enumerate(items):
            trade_id, version = _describe(item)
            try:
                trade, created = service.submit_trade(TradeCreate.model_validate(item))
                results.append(
                    BulkItemResult(
                        index=index,
                        trade_id=trade.trade_id,
                        version=trade.version,
                        status="created" if created else "replaced",
                    )
                )
            except ValidationError as exc:
                detail = "; ".join(
                    f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                    for err in exc.errors()
                )
                results.append(
                    BulkItemResult(
                        index=index, trade_id=trade_id, version=version,
                        status="rejected", detail=detail,
                    )
                )
            except TradeStoreError as exc:
                results.append(
                    BulkItemResult(
                        index=index, trade_id=trade_id, version=version,
                        status="rejected", detail=str(exc),
                    )
                )

        summary = BulkSummary(
            total=len(results),
            created=sum(r.status == "created" for r in results),
            replaced=sum(r.status == "replaced" for r in results),
            rejected=sum(r.status == "rejected" for r in results),
        )
        return BulkResponse(summary=summary, results=results)

    @app.get("/trades", response_model=list[TradeOut])
    def list_trades(expired: bool | None = None, service: TradeService = Depends(get_service)):
        return service.list_trades(expired)

    @app.get("/trades/{trade_id}", response_model=list[TradeOut])
    def get_trade_versions(trade_id: str, service: TradeService = Depends(get_service)):
        return service.get_versions(trade_id)

    @app.get("/trades/{trade_id}/versions/{version}", response_model=TradeOut)
    def get_trade_version(
        trade_id: str, version: int, service: TradeService = Depends(get_service)
    ):
        return service.get_trade(trade_id, version)

    return app


app = create_app()