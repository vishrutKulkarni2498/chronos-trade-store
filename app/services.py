"""Business rules R1-R4 live here, independent of HTTP and of the database."""
from datetime import date

from app.clock import Clock, today_utc
from app.domain import Trade
from app.exceptions import (
    DuplicateTradeError,
    LowerVersionError,
    PastMaturityDateError,
    TradeNotFoundError,
)
from app.models import TradeModel
from app.repository import TradeRepository
from app.schemas import TradeCreate


class TradeService:
    def __init__(self, repository: TradeRepository, clock: Clock = today_utc) -> None:
        self._repository = repository
        self._clock = clock

    def submit_trade(self, data: TradeCreate) -> tuple[Trade, bool]:
        """Validate and store a trade.

        Returns (trade, created). created is False when an existing record with
        the same (trade_id, version) was replaced.
        """
        today = self._clock()

        # R3: maturity date strictly before today is rejected (A4: today is valid).
        if data.maturity_date < today:
            raise PastMaturityDateError(data.trade_id, data.maturity_date, today)

        # R1: lower than the highest stored version is rejected (A2).
        stored_max = self._repository.max_version(data.trade_id)
        if stored_max is not None and data.version < stored_max:
            raise LowerVersionError(data.trade_id, data.version, stored_max)

        # R2: same version replaces the existing record (A3).
        existing = self._repository.get(data.trade_id, data.version)
        if existing is not None:
            return self._replace(existing, data, today), False

        new_trade = TradeModel(
            trade_id=data.trade_id,
            version=data.version,
            counter_party_id=data.counter_party_id,
            portfolio_id=data.portfolio_id,
            maturity_date=data.maturity_date,
            created_date=today,
            expired=False,
        )
        try:
            stored = self._repository.add(new_trade)
        except DuplicateTradeError:
            # A concurrent request inserted the same key first (A15): treat as a replace.
            existing = self._repository.get(data.trade_id, data.version)
            if existing is None:
                raise
            return self._replace(existing, data, today), False
        return self._to_domain(stored, today), True

    def get_versions(self, trade_id: str) -> list[Trade]:
        rows = self._repository.list_versions(trade_id)
        if not rows:
            raise TradeNotFoundError(trade_id)
        today = self._clock()
        return [self._to_domain(row, today) for row in rows]

    def get_trade(self, trade_id: str, version: int) -> Trade:
        row = self._repository.get(trade_id, version)
        if row is None:
            raise TradeNotFoundError(trade_id, version)
        return self._to_domain(row, self._clock())

    def list_trades(self, expired: bool | None = None) -> list[Trade]:
        today = self._clock()
        rows = self._repository.list_all(today, expired)
        return [self._to_domain(row, today) for row in rows]

    def expire_matured_trades(self) -> int:
        """R4: persist expired=True for every trade whose maturity date has passed."""
        return self._repository.mark_expired(self._clock())

    def _replace(self, existing: TradeModel, data: TradeCreate, today: date) -> Trade:
        updated = self._repository.replace(
            existing,
            counter_party_id=data.counter_party_id,
            portfolio_id=data.portfolio_id,
            maturity_date=data.maturity_date,
        )
        return self._to_domain(updated, today)

    @staticmethod
    def _to_domain(row: TradeModel, today: date) -> Trade:
        # A6: expiry is also derived at read time, so results are correct
        # between runs of the scheduled job.
        return Trade(
            trade_id=row.trade_id,
            version=row.version,
            counter_party_id=row.counter_party_id,
            portfolio_id=row.portfolio_id,
            maturity_date=row.maturity_date,
            created_date=row.created_date,
            expired=bool(row.expired) or row.maturity_date < today,
        )