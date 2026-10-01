from datetime import timedelta

import pytest

from app.exceptions import LowerVersionError, PastMaturityDateError, TradeNotFoundError


# ---- accepting trades ---------------------------------------------------------
def test_accepts_valid_new_trade(service, make_trade, clock):
    trade, created = service.submit_trade(make_trade())

    assert created is True
    assert (trade.trade_id, trade.version) == ("T1", 1)
    assert trade.created_date == clock()
    assert trade.expired is False


def test_first_ever_submission_may_have_any_version(service, make_trade):
    trade, created = service.submit_trade(make_trade(version=5))
    assert created is True
    assert trade.version == 5


# ---- R3: maturity date --------------------------------------------------------
def test_rejects_trade_with_past_maturity_date(service, repository, make_trade, clock):
    with pytest.raises(PastMaturityDateError):
        service.submit_trade(make_trade(maturity_date=clock() - timedelta(days=1)))
    assert repository.get("T1", 1) is None  # nothing stored


def test_accepts_trade_maturing_today(service, make_trade, clock):
    trade, created = service.submit_trade(make_trade(maturity_date=clock()))
    assert created is True
    assert trade.expired is False


def test_maturity_check_takes_precedence_over_version_check(service, make_trade, clock):
    service.submit_trade(make_trade(version=2))
    with pytest.raises(PastMaturityDateError):
        service.submit_trade(make_trade(version=1, maturity_date=clock() - timedelta(days=1)))


# ---- R1: lower version --------------------------------------------------------
def test_rejects_lower_version(service, make_trade):
    service.submit_trade(make_trade(trade_id="T2", version=2, counter_party_id="CP-2"))

    with pytest.raises(LowerVersionError):
        service.submit_trade(make_trade(trade_id="T2", version=1, counter_party_id="CP-1"))

    assert [t.version for t in service.get_versions("T2")] == [2]


def test_rejects_lower_version_even_when_several_versions_exist(service, make_trade):
    service.submit_trade(make_trade(version=1))
    service.submit_trade(make_trade(version=3))

    with pytest.raises(LowerVersionError):
        service.submit_trade(make_trade(version=2))


def test_version_rule_is_per_trade_id(service, make_trade):
    service.submit_trade(make_trade(trade_id="T1", version=5))
    trade, created = service.submit_trade(make_trade(trade_id="T2", version=1))
    assert created is True


# ---- R2: same version replaces -------------------------------------------------
def test_same_version_replaces_existing_record(service, make_trade, clock):
    service.submit_trade(make_trade(counter_party_id="CP-1", portfolio_id="B1"))
    new_maturity = clock() + timedelta(days=500)

    trade, created = service.submit_trade(
        make_trade(counter_party_id="CP-9", portfolio_id="B7", maturity_date=new_maturity)
    )

    assert created is False
    stored = service.get_versions("T1")
    assert len(stored) == 1
    assert stored[0].counter_party_id == "CP-9"
    assert stored[0].portfolio_id == "B7"
    assert stored[0].maturity_date == new_maturity


def test_replacement_preserves_original_created_date(service, make_trade, clock):
    original_date = clock()
    service.submit_trade(make_trade())
    clock.advance(3)

    trade, created = service.submit_trade(make_trade(counter_party_id="CP-2"))

    assert created is False
    assert trade.created_date == original_date


# ---- higher version / history --------------------------------------------------
def test_higher_version_is_stored_as_new_row_and_history_is_retained(service, make_trade):
    service.submit_trade(make_trade(trade_id="T2", version=1, counter_party_id="CP-1"))

    trade, created = service.submit_trade(
        make_trade(trade_id="T2", version=2, counter_party_id="CP-2")
    )

    assert created is True
    versions = service.get_versions("T2")
    assert [(t.version, t.counter_party_id) for t in versions] == [(1, "CP-1"), (2, "CP-2")]


# ---- lookups ---------------------------------------------------------------------
def test_get_versions_raises_for_unknown_trade(service):
    with pytest.raises(TradeNotFoundError):
        service.get_versions("NOPE")


def test_get_trade_raises_for_unknown_version(service, make_trade):
    service.submit_trade(make_trade())
    with pytest.raises(TradeNotFoundError):
        service.get_trade("T1", 99)


def test_list_trades_returns_everything_ordered(service, make_trade):
    service.submit_trade(make_trade(trade_id="T2", version=1))
    service.submit_trade(make_trade(trade_id="T1", version=1))
    service.submit_trade(make_trade(trade_id="T2", version=2))

    keys = [(t.trade_id, t.version) for t in service.list_trades()]
    assert keys == [("T1", 1), ("T2", 1), ("T2", 2)]


# ---- R4: expiry ------------------------------------------------------------------
def test_expiry_marks_only_matured_trades(service, repository, make_trade, clock):
    service.submit_trade(make_trade(trade_id="SOON", maturity_date=clock() + timedelta(days=2)))
    service.submit_trade(make_trade(trade_id="LATER", maturity_date=clock() + timedelta(days=100)))
    clock.advance(3)

    assert service.expire_matured_trades() == 1
    assert repository.get("SOON", 1).expired is True
    assert repository.get("LATER", 1).expired is False


def test_expiry_is_idempotent(service, make_trade, clock):
    service.submit_trade(make_trade(maturity_date=clock() + timedelta(days=1)))
    clock.advance(2)
    assert service.expire_matured_trades() == 1
    assert service.expire_matured_trades() == 0


def test_trade_maturing_today_is_not_expired_until_tomorrow(service, repository, make_trade, clock):
    service.submit_trade(make_trade(maturity_date=clock()))

    assert service.expire_matured_trades() == 0
    assert service.get_trade("T1", 1).expired is False

    clock.advance(1)
    assert service.expire_matured_trades() == 1
    assert service.get_trade("T1", 1).expired is True


def test_expired_flag_is_correct_at_read_time_before_the_job_runs(
    service, repository, make_trade, clock
):
    service.submit_trade(make_trade(maturity_date=clock() + timedelta(days=2)))
    clock.advance(3)  # matured, but the scheduled job has not run yet

    assert repository.get("T1", 1).expired is False  # persisted flag is stale
    assert service.get_trade("T1", 1).expired is True  # derived at read time (A6)


def test_list_trades_filters_by_effective_expiry(service, make_trade, clock):
    service.submit_trade(make_trade(trade_id="SOON", maturity_date=clock() + timedelta(days=2)))
    service.submit_trade(make_trade(trade_id="LATER", maturity_date=clock() + timedelta(days=100)))
    clock.advance(3)

    assert [t.trade_id for t in service.list_trades(expired=True)] == ["SOON"]
    assert [t.trade_id for t in service.list_trades(expired=False)] == ["LATER"]
    assert len(service.list_trades()) == 2