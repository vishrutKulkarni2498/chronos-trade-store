"""Section: read trades."""
from fastapi import APIRouter, Depends

from app.dependencies import get_service
from app.routers.tags import READ
from app.schemas import TradeOut
from app.services import TradeService

router = APIRouter(tags=[READ])


@router.get("/trades", response_model=list[TradeOut])
def list_trades(expired: bool | None = None, service: TradeService = Depends(get_service)):
    """All stored trades, ordered by trade id then version. Filter with `?expired=true|false`."""
    return service.list_trades(expired)


@router.get("/trades/{trade_id}", response_model=list[TradeOut])
def get_trade_versions(trade_id: str, service: TradeService = Depends(get_service)):
    """Every stored version of one trade. 404 if the trade does not exist."""
    return service.get_versions(trade_id)


@router.get("/trades/{trade_id}/versions/{version}", response_model=TradeOut)
def get_trade_version(
    trade_id: str, version: int, service: TradeService = Depends(get_service)
):
    """One specific version of a trade. 404 if it does not exist."""
    return service.get_trade(trade_id, version)