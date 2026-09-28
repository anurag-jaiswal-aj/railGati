import typing
from fastapi.testclient import TestClient
from tests.services.test_network_station_pair_intermediate_hubs import hub_concentration_fixtures  # noqa: F401


def test_api_hub_concentration_success(client: TestClient, hub_concentration_fixtures: dict[str, typing.Any]) -> None:
    res = client.get("/api/v1/network/stations/A/D/intermediate-hubs")
    assert res.status_code == 200
    data = res.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "D"
    assert data["total_traversal_instances"] > 0
    assert len(data["intermediate_hubs"]) > 0

    first_hub = data["intermediate_hubs"][0]
    assert "station_code" in first_hub
    assert "traversal_instance_count" in first_hub
    assert "occurrence_count" in first_hub

def test_api_hub_concentration_not_found(client: TestClient, hub_concentration_fixtures: dict[str, typing.Any]) -> None:
    res = client.get("/api/v1/network/stations/UNKNOWN/D/intermediate-hubs")
    assert res.status_code == 404
