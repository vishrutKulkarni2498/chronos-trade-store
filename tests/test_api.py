from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(clock):
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=False)
    return TestClient(app)


@pytest.fixture
def make_payload(clock):
    def _make(**overrides) -> dict:
        data = {
            "trade_id": "T1",
            "version": 1,
            "counter_party_id": "CP-1",
            "portfolio_id": "B1",
            "maturity_date": (clock() + timedelta(days=365)).isoformat(),
        }
        data.update(overrides)
        return data

    return _make


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---- POST /trades ----------------------------------------------------------------
def test_post_new_trade_returns_201(client, make_payload, clock):
    response = client.post("/trades", json=make_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["trade_id"] == "T1"
    assert body["version"] == 1
    assert body["created_date"] == clock().isoformat()
    assert body["expired"] is False


def test_post_same_version_returns_200_and_replaces(client, make_payload):
    client.post("/trades", json=make_payload())

    response = client.post("/trades", json=make_payload(counter_party_id="CP-9"))

    assert response.status_code == 200
    assert response.json()["counter_party_id"] == "CP-9"
    assert len(client.get("/trades/T1").json()) == 1


def test_post_lower_version_returns_409(client, make_payload):
    client.post("/trades", json=make_payload(trade_id="T2", version=2))

    response = client.post("/trades", json=make_payload(trade_id="T2", version=1))

    assert response.status_code == 409
    assert "lower" in response.json()["detail"]


def test_post_higher_version_returns_201_and_keeps_history(client, make_payload):
    client.post("/trades", json=make_payload(trade_id="T2", version=1))

    response = client.post("/trades", json=make_payload(trade_id="T2", version=2))

    assert response.status_code == 201
    assert [t["version"] for t in client.get("/trades/T2").json()] == [1, 2]


def test_post_past_maturity_returns_422(client, make_payload, clock):
    past = (clock() - timedelta(days=1)).isoformat()

    response = client.post("/trades", json=make_payload(maturity_date=past))

    assert response.status_code == 422
    assert "earlier than today" in response.json()["detail"]
    assert client.get("/trades").json() == []


def test_post_maturity_today_returns_201(client, make_payload, clock):
    response = client.post("/trades", json=make_payload(maturity_date=clock().isoformat()))
    assert response.status_code == 201


@pytest.mark.parametrize(
    "override",
    [
        {"version": 0},
        {"version": -1},
        {"trade_id": ""},
        {"trade_id": "   "},
        {"maturity_date": "not-a-date"},
    ],
)
def test_post_invalid_payload_returns_422(client, make_payload, override):
    assert client.post("/trades", json=make_payload(**override)).status_code == 422


def test_post_missing_field_returns_422(client, make_payload):
    payload = make_payload()
    del payload["portfolio_id"]
    assert client.post("/trades", json=payload).status_code == 422


def test_client_supplied_created_date_is_ignored(client, make_payload, clock):
    response = client.post("/trades", json=make_payload(created_date="2015-03-14", expired=True))

    assert response.status_code == 201
    assert response.json()["created_date"] == clock().isoformat()
    assert response.json()["expired"] is False


# ---- GET endpoints ---------------------------------------------------------------
def test_get_trades_is_ordered_by_trade_id_then_version(client, make_payload):
    client.post("/trades", json=make_payload(trade_id="T2", version=1))
    client.post("/trades", json=make_payload(trade_id="T2", version=2))
    client.post("/trades", json=make_payload(trade_id="T1", version=1))

    keys = [(t["trade_id"], t["version"]) for t in client.get("/trades").json()]
    assert keys == [("T1", 1), ("T2", 1), ("T2", 2)]


def test_get_unknown_trade_returns_404(client):
    assert client.get("/trades/NOPE").status_code == 404


def test_get_single_version(client, make_payload):
    client.post("/trades", json=make_payload(version=1))

    assert client.get("/trades/T1/versions/1").status_code == 200
    assert client.get("/trades/T1/versions/7").status_code == 404


def test_expired_flag_and_filter_reflect_the_passage_of_time(client, make_payload, clock):
    soon = (clock() + timedelta(days=2)).isoformat()
    client.post("/trades", json=make_payload(trade_id="SOON", maturity_date=soon))
    client.post("/trades", json=make_payload(trade_id="LATER"))
    clock.advance(3)

    everything = {t["trade_id"]: t["expired"] for t in client.get("/trades").json()}
    assert everything == {"SOON": True, "LATER": False}
    assert [t["trade_id"] for t in client.get("/trades?expired=true").json()] == ["SOON"]
    assert [t["trade_id"] for t in client.get("/trades?expired=false").json()] == ["LATER"]


# ---- POST /trades/bulk -----------------------------------------------------------
def test_bulk_reports_per_trade_results(client, make_payload, clock):
    past = (clock() - timedelta(days=1)).isoformat()
    batch = [
        make_payload(trade_id="T1", version=1),
        make_payload(trade_id="T1", version=1, counter_party_id="CP-2"),  # replaces
        make_payload(trade_id="T2", version=2),
        make_payload(trade_id="T2", version=1),  # lower version
        make_payload(trade_id="T3", maturity_date=past),  # past maturity
        {"trade_id": "T4"},  # invalid payload
    ]

    response = client.post("/trades/bulk", json=batch)

    assert response.status_code == 200
    body = response.json()
    assert [r["status"] for r in body["results"]] == [
        "created", "replaced", "created", "rejected", "rejected", "rejected",
    ]
    assert body["summary"] == {"total": 6, "created": 2, "replaced": 1, "rejected": 3}
    assert body["results"][3]["trade_id"] == "T2"
    assert "lower" in body["results"][3]["detail"]


def test_bulk_handles_non_object_items_and_empty_batch(client):
    response = client.post("/trades/bulk", json=[42])
    assert response.json()["summary"]["rejected"] == 1

    empty = client.post("/trades/bulk", json=[])
    assert empty.status_code == 200
    assert empty.json()["summary"]["total"] == 0


# ---- application lifecycle -------------------------------------------------------
def test_lifespan_starts_and_stops_the_scheduler(clock):
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=True)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200