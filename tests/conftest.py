import os

# Must be set before anything imports app.main (which builds a module-level app).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ENABLE_SCHEDULER"] = "false"

from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import make_engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.repository import TradeRepository  # noqa: E402
from app.schemas import TradeCreate  # noqa: E402
from app.services import TradeService  # noqa: E402

TODAY = date(2026, 9, 30)


class FakeClock:
    """Controllable 'today' for deterministic date tests."""

    def __init__(self, today: date = TODAY) -> None:
        self.today = today

    def __call__(self) -> date:
        return self.today

    def advance(self, days: int) -> None:
        self.today += timedelta(days=days)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def engine():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def repository(session) -> TradeRepository:
    return TradeRepository(session)


@pytest.fixture
def service(repository, clock) -> TradeService:
    return TradeService(repository, clock)


@pytest.fixture
def make_trade(clock):
    """Factory for valid TradeCreate objects; override any field by keyword."""

    def _make(**overrides) -> TradeCreate:
        data = {
            "trade_id": "T1",
            "version": 1,
            "counter_party_id": "CP-1",
            "portfolio_id": "B1",
            "maturity_date": clock() + timedelta(days=365),
        }
        data.update(overrides)
        return TradeCreate(**data)

    return _make