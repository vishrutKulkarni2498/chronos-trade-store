"""Persistence only. No business rules live here."""
from datetime import date

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import DuplicateTradeError
from app.models import TradeModel


class TradeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, trade_id: str, version: int) -> TradeModel | None:
        return self._session.get(TradeModel, (trade_id, version))

    def max_version(self, trade_id: str) -> int | None:
        stmt = select(func.max(TradeModel.version)).where(TradeModel.trade_id == trade_id)
        return self._session.scalar(stmt)

    def list_versions(self, trade_id: str) -> list[TradeModel]:
        stmt = (
            select(TradeModel)
            .where(TradeModel.trade_id == trade_id)
            .order_by(TradeModel.version)
        )
        return list(self._session.scalars(stmt))

    def list_all(self, today: date, expired: bool | None = None) -> list[TradeModel]:
        stmt = select(TradeModel).order_by(TradeModel.trade_id, TradeModel.version)
        if expired is True:
            stmt = stmt.where(
                or_(TradeModel.expired.is_(True), TradeModel.maturity_date < today)
            )
        elif expired is False:
            stmt = stmt.where(
                and_(TradeModel.expired.is_(False), TradeModel.maturity_date >= today)
            )
        return list(self._session.scalars(stmt))

    def add(self, trade: TradeModel) -> TradeModel:
        try:
            self._session.add(trade)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateTradeError(trade.trade_id, trade.version) from exc
        return trade

    def replace(
        self,
        trade: TradeModel,
        *,
        counter_party_id: str,
        portfolio_id: str,
        maturity_date: date,
    ) -> TradeModel:
        trade.counter_party_id = counter_party_id
        trade.portfolio_id = portfolio_id
        trade.maturity_date = maturity_date
        trade.expired = False
        self._session.commit()
        return trade

    def mark_expired(self, today: date) -> int:
        stmt = (
            update(TradeModel)
            .where(TradeModel.maturity_date < today, TradeModel.expired.is_(False))
            .values(expired=True)
        )
        result = self._session.execute(stmt, execution_options={"synchronize_session": False})
        count = result.rowcount
        self._session.commit()
        self._session.expire_all()  # make already-loaded objects reflect the bulk update
        return count