"""Section: submit trades."""
from typing import Any

from fastapi import APIRouter, Body, Depends, Response
from pydantic import ValidationError

from app.dependencies import get_service
from app.exceptions import TradeStoreError
from app.routers.tags import SUBMIT
from app.schemas import BulkItemResult, BulkResponse, BulkSummary, TradeCreate, TradeOut
from app.services import TradeService

router = APIRouter(tags=[SUBMIT])


def _describe(item: Any) -> tuple[str | None, int | None]:
    """Best-effort trade_id/version from a raw bulk item, for error reporting."""
    if not isinstance(item, dict):
        return None, None
    raw_id = item.get("trade_id")
    raw_version = item.get("version")
    trade_id = str(raw_id) if raw_id is not None else None
    is_int = isinstance(raw_version, int) and not isinstance(raw_version, bool)
    return trade_id, raw_version if is_int else None


@router.post("/trades", response_model=TradeOut, status_code=201)
def submit_trade(
    payload: TradeCreate,
    response: Response,
    service: TradeService = Depends(get_service),
):
    """Store one trade. Returns 201 for a new trade or version, 200 when the same
    version replaced the existing record, 409 for a lower version, and 422 for a
    past maturity date or invalid input."""
    trade, created = service.submit_trade(payload)
    if not created:
        response.status_code = 200  # same version replaced the existing record
    return trade


@router.post("/trades/bulk", response_model=BulkResponse)
def submit_bulk(
    items: list[Any] = Body(...),
    service: TradeService = Depends(get_service),
):
    """Store many trades. Each is validated independently, and the response reports
    a per-trade result, so one bad trade does not block the others."""
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
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
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