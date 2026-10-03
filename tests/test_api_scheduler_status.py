from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def test_status_when_scheduler_is_disabled(clock):
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=False)

    response = TestClient(app).get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["running"] is False
    assert body["job_id"] == "expire-matured-trades"
    assert body["next_run_time"] is None
    assert body["last_run"] is None
    assert body["totals"] == {"runs": 0, "failures": 0, "trades_expired": 0}


def test_status_when_scheduler_is_enabled(clock, monkeypatch):
    monkeypatch.setenv("EXPIRY_JOB_INTERVAL_MINUTES", "7")
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=True)

    with TestClient(app) as client:
        body = client.get("/scheduler/status").json()

    now = datetime.now(timezone.utc)
    next_run = datetime.fromisoformat(body["next_run_time"])
    assert body["enabled"] is True
    assert body["running"] is True
    assert body["interval_minutes"] == 7
    assert now < next_run <= now + timedelta(minutes=7, seconds=5)

    last = body["last_run"]
    assert last["trigger"] == "startup"  # the catch-up run at application start
    assert last["success"] is True
    assert last["trades_expired"] == 0
    assert last["error"] is None
    assert body["totals"] == {"runs": 1, "failures": 0, "trades_expired": 0}


def test_status_uses_the_injected_clock_for_run_timestamps(clock):
    moment = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    app = create_app(
        database_url="sqlite://", clock=clock, enable_scheduler=True, now=lambda: moment
    )

    with TestClient(app) as client:
        last = client.get("/scheduler/status").json()["last_run"]

    assert datetime.fromisoformat(last["started_at"]) == moment
    assert datetime.fromisoformat(last["finished_at"]) == moment
    assert last["duration_ms"] == 0


def test_a_failed_startup_run_does_not_stop_the_api(clock, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.main.run_expiry_job", boom)
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=True)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/scheduler/status").json()["running"] is True


def test_status_reports_not_running_after_shutdown(clock):
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=True)
    client = TestClient(app)

    with client:
        assert client.get("/scheduler/status").json()["running"] is True

    assert client.get("/scheduler/status").json()["running"] is False


IST_OFFSET = timedelta(hours=5, minutes=30)


def test_status_shows_current_time_in_utc_and_ist(clock):
    moment = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    app = create_app(
        database_url="sqlite://", clock=clock, enable_scheduler=False, now=lambda: moment
    )

    body = TestClient(app).get("/scheduler/status").json()

    current_utc = datetime.fromisoformat(body["current_time_utc"])
    current_ist = datetime.fromisoformat(body["current_time_ist"])
    assert current_utc == moment
    assert current_ist == moment  # the same instant
    assert current_ist.utcoffset() == IST_OFFSET
    assert body["current_time_ist"].startswith("2026-09-30T17:30:00")
    assert body["current_time_ist"].endswith("+05:30")


def test_status_shows_ist_beside_every_utc_time(clock):
    moment = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    app = create_app(
        database_url="sqlite://", clock=clock, enable_scheduler=True, now=lambda: moment
    )

    with TestClient(app) as client:
        body = client.get("/scheduler/status").json()

    next_utc = datetime.fromisoformat(body["next_run_time"])
    next_ist = datetime.fromisoformat(body["next_run_time_ist"])
    assert next_ist == next_utc
    assert next_ist.utcoffset() == IST_OFFSET

    last = body["last_run"]
    for utc_key, ist_key in [("started_at", "started_at_ist"), ("finished_at", "finished_at_ist")]:
        assert datetime.fromisoformat(last[ist_key]) == datetime.fromisoformat(last[utc_key])
        assert datetime.fromisoformat(last[ist_key]).utcoffset() == IST_OFFSET


def test_status_keeps_the_existing_utc_fields(clock):
    moment = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    app = create_app(
        database_url="sqlite://", clock=clock, enable_scheduler=True, now=lambda: moment
    )

    with TestClient(app) as client:
        body = client.get("/scheduler/status").json()

    assert datetime.fromisoformat(body["next_run_time"]).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(body["last_run"]["started_at"]).utcoffset() == timedelta(0)


def test_ist_times_are_null_when_there_is_nothing_to_show(clock):
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=False)

    body = TestClient(app).get("/scheduler/status").json()

    assert body["next_run_time_ist"] is None
    assert body["last_run"] is None
    assert body["current_time_ist"] is not None  # the current time is always shown