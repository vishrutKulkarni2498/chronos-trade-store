import pytest
from pydantic import ValidationError

from app.schemas import TradeCreate

VALID = {
    "trade_id": "T1",
    "version": 1,
    "counter_party_id": "CP-1",
    "portfolio_id": "B1",
    "maturity_date": "2030-05-20",
}


def test_valid_payload_is_accepted():
    trade = TradeCreate(**VALID)
    assert trade.trade_id == "T1"
    assert trade.maturity_date.isoformat() == "2030-05-20"


def test_surrounding_whitespace_is_stripped():
    trade = TradeCreate(**{**VALID, "trade_id": "  T1  "})
    assert trade.trade_id == "T1"


@pytest.mark.parametrize("missing", list(VALID))
def test_missing_field_is_rejected(missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValidationError):
        TradeCreate(**payload)


@pytest.mark.parametrize("field", ["trade_id", "counter_party_id", "portfolio_id"])
@pytest.mark.parametrize("value", ["", "   "])
def test_blank_identifiers_are_rejected(field, value):
    with pytest.raises(ValidationError):
        TradeCreate(**{**VALID, field: value})


@pytest.mark.parametrize("version", [0, -1])
def test_non_positive_version_is_rejected(version):
    with pytest.raises(ValidationError):
        TradeCreate(**{**VALID, "version": version})


def test_invalid_date_is_rejected():
    with pytest.raises(ValidationError):
        TradeCreate(**{**VALID, "maturity_date": "not-a-date"})


def test_client_supplied_created_date_and_expired_are_ignored():
    trade = TradeCreate(**{**VALID, "created_date": "2015-03-14", "expired": True})
    assert not hasattr(trade, "created_date")
    assert not hasattr(trade, "expired")