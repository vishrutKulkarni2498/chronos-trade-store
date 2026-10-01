"""Domain exceptions. The API layer maps these to HTTP status codes."""
from datetime import date


class TradeStoreError(Exception):
    """Base class for all trade store errors."""


class LowerVersionError(TradeStoreError):
    """Incoming trade has a lower version than the stored maximum (rule R1)."""

    def __init__(self, trade_id: str, incoming_version: int, stored_version: int) -> None:
        self.trade_id = trade_id
        self.incoming_version = incoming_version
        self.stored_version = stored_version
        super().__init__(
            f"Trade {trade_id} version {incoming_version} is lower than "
            f"existing version {stored_version}."
        )


class PastMaturityDateError(TradeStoreError):
    """Incoming trade has a maturity date earlier than today (rule R3)."""

    def __init__(self, trade_id: str, maturity_date: date, today: date) -> None:
        self.trade_id = trade_id
        self.maturity_date = maturity_date
        super().__init__(
            f"Trade {trade_id} has maturity date {maturity_date.isoformat()}, "
            f"which is earlier than today ({today.isoformat()})."
        )


class TradeNotFoundError(TradeStoreError):
    def __init__(self, trade_id: str, version: int | None = None) -> None:
        self.trade_id = trade_id
        self.version = version
        target = f"Trade {trade_id}" if version is None else f"Trade {trade_id} version {version}"
        super().__init__(f"{target} was not found.")


class DuplicateTradeError(TradeStoreError):
    """(trade_id, version) already exists. Raised by the repository on a key clash."""

    def __init__(self, trade_id: str, version: int) -> None:
        self.trade_id = trade_id
        self.version = version
        super().__init__(f"Trade {trade_id} version {version} already exists.")