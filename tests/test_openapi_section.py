import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def spec(clock):
    app = create_app(database_url="sqlite://", clock=clock, enable_scheduler=False)
    return TestClient(app).get("/openapi.json").json()


def test_submit_endpoints_are_in_the_submit_section(spec):
    assert spec["paths"]["/trades"]["post"]["tags"] == ["Submit trades"]
    assert spec["paths"]["/trades/bulk"]["post"]["tags"] == ["Submit trades"]


def test_read_endpoints_are_in_the_read_section(spec):
    assert spec["paths"]["/trades"]["get"]["tags"] == ["Read trades"]
    assert spec["paths"]["/trades/{trade_id}"]["get"]["tags"] == ["Read trades"]
    version_path = spec["paths"]["/trades/{trade_id}/versions/{version}"]
    assert version_path["get"]["tags"] == ["Read trades"]


def test_scheduler_endpoint_is_in_the_scheduler_section(spec):
    assert spec["paths"]["/scheduler/status"]["get"]["tags"] == ["Scheduler"]


def test_health_endpoint_is_in_the_system_section(spec):
    assert spec["paths"]["/health"]["get"]["tags"] == ["System"]


def test_sections_are_listed_in_order_with_descriptions(spec):
    names = [tag["name"] for tag in spec["tags"]]
    assert names == ["Submit trades", "Read trades", "Scheduler", "System"]
    assert all(tag["description"] for tag in spec["tags"])