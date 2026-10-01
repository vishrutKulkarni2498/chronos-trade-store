"""SQLAlchemy persistence model.

The composite primary key (trade_id, version) also serves as the index for
"highest version of a trade" lookups, since trade_id is its leading column.
"""
from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TradeModel(Base):
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    counter_party_id: Mapped[str] = mapped_column(String(64), nullable=False)
    portfolio_id: Mapped[str] = mapped_column(String(64), nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_date: Mapped[date] = mapped_column(Date, nullable=False)
    expired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)