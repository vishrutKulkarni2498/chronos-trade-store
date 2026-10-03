"""Maps domain exceptions to HTTP responses."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import LowerVersionError, PastMaturityDateError, TradeNotFoundError

STATUS_BY_ERROR = {
    LowerVersionError: 409,  # conflicts with the stored version (R1)
    PastMaturityDateError: 422,  # invalid on its own (R3)
    TradeNotFoundError: 404,
}


def _handler_for(status_code: int):
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


def register_exception_handlers(app: FastAPI) -> None:
    for error_type, status_code in STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _handler_for(status_code))