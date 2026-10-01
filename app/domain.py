"""Plain domain object returned by the service layer."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Trade:
    trade_id: str
    version: int
    counter_party_id: str
    portfolio_id: str
    maturity_date: date
    created_date: date
    expired: bool