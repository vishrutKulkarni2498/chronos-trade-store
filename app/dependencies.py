"""Dependencies shared by the routers.

The session factory and clock are read from app.state, which create_app fills in,
so each application instance (including those built in tests) uses its own.
"""
from collections.abc import Iterator

from fastapi import Request

from app.repository import TradeRepository
from app.services import TradeService


def get_service(request: Request) -> Iterator[TradeService]:
    state = request.app.state
    session = state.session_factory()
    try:
        yield TradeService(TradeRepository(session), state.clock)
    finally:
        session.close()