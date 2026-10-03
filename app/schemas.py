"""Request/response schemas (API contract and input validation, assumption A11)."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TradeCreate(BaseModel):
    """Incoming trade. created_date and expired are server-controlled (A9) and
    are ignored if a client supplies them."""

    trade_id: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)
    counter_party_id: str = Field(min_length=1, max_length=64)
    portfolio_id: str = Field(min_length=1, max_length=64)
    maturity_date: date

    @field_validator("trade_id", "counter_party_id", "portfolio_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_id: str
    version: int
    counter_party_id: str
    portfolio_id: str
    maturity_date: date
    created_date: date
    expired: bool


class BulkItemResult(BaseModel):
    index: int
    trade_id: Optional[str] = None
    version: Optional[int] = None
    status: Literal["created", "replaced", "rejected"]
    detail: Optional[str] = None


class BulkSummary(BaseModel):
    total: int
    created: int
    replaced: int
    rejected: int


class BulkResponse(BaseModel):
    summary: BulkSummary
    results: list[BulkItemResult]


class RunRecordOut(BaseModel):
    trigger: str
    started_at: datetime
    started_at_ist: datetime
    finished_at: datetime
    finished_at_ist: datetime
    duration_ms: int
    success: bool
    trades_expired: int
    error: Optional[str] = None


class SchedulerTotals(BaseModel):
    runs: int
    failures: int
    trades_expired: int


class SchedulerStatusOut(BaseModel):
    enabled: bool
    running: bool
    interval_minutes: int
    job_id: str
    current_time_utc: datetime
    current_time_ist: datetime
    next_run_time: Optional[datetime] = None
    next_run_time_ist: Optional[datetime] = None
    last_run: Optional[RunRecordOut] = None
    totals: SchedulerTotals 