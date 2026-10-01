from datetime import date

import pytest

from app.exceptions import DuplicateTradeError
from app.models import TradeModel

TODAY = date(2026, 9, 30)


def _row(trade_id="T1", version=1, maturity=date(2030, 1, 1), expired=False):
    return TradeModel(
        trade_id=trade_id,
        version=version,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=maturity,
        created_date=TODAY,
        expired=expired,
    )


def test_max_version_is_none_when_trade_unknown(repository):
    assert repository.max_version("NOPE") is None


def test_max_version_returns_highest_stored_version(repository):
    repository.add(_row(version=1))
    repository.add(_row(version=3))
    repository.add(_row(version=2))
    assert repository.max_version("T1") == 3


def test_adding_duplicate_key_raises_and_session_stays_usable(repository):
    repository.add(_row(version=1))
    with pytest.raises(DuplicateTradeError):
        repository.add(_row(version=1))
    # the failed insert must not poison the session
    repository.add(_row(version=2))
    assert repository.max_version("T1") == 2


def test_list_versions_is_ordered_by_version(repository):
    repository.add(_row(version=2))
    repository.add(_row(version=1))
    assert [r.version for r in repository.list_versions("T1")] == [1, 2]


def test_list_all_is_ordered_by_trade_id_then_version(repository):
    repository.add(_row("T2", 2))
    repository.add(_row("T1", 1))
    repository.add(_row("T2", 1))
    keys = [(r.trade_id, r.version) for r in repository.list_all(TODAY)]
    assert keys == [("T1", 1), ("T2", 1), ("T2", 2)]


def test_mark_expired_updates_only_matured_unexpired_rows(repository):
    repository.add(_row("OLD", maturity=date(2026, 9, 29)))
    repository.add(_row("TODAY", maturity=date(2026, 9, 30)))
    repository.add(_row("FUTURE", maturity=date(2030, 1, 1)))

    assert repository.mark_expired(TODAY) == 1
    assert repository.get("OLD", 1).expired is True
    assert repository.get("TODAY", 1).expired is False
    assert repository.get("FUTURE", 1).expired is False
    assert repository.mark_expired(TODAY) == 0  # idempotent