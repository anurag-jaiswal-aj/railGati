from fastapi.testclient import TestClient
from tests.services.test_network_station_pair_route_diversity import route_diversity_fixtures  # noqa: F401


def test_api_station_pair_route_diversity_success(client: TestClient, route_diversity_fixtures: dict) -> None:
    res = client.get("/api/v1/network/stations/A/D/route-diversity")
    assert res.status_code == 200

    data = res.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "D"
    assert data["distinct_path_count"] == 8
    assert len(data["paths"]) == 8

def test_api_station_pair_route_diversity_not_found(client: TestClient, route_diversity_fixtures: dict) -> None:
    res = client.get("/api/v1/network/stations/UNKNOWN/D/route-diversity")
    assert res.status_code == 404
