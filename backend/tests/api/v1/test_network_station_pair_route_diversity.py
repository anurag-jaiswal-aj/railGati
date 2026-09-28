from fastapi.testclient import TestClient


def test_api_station_pair_route_diversity_success(client: TestClient, route_diversity_fixtures: dict) -> None:
    res = client.get("/api/v1/network/stations/A/D/route-diversity")
    assert res.status_code == 200

    data = res.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "D"
    assert data["distinct_path_count"] == 4
    assert len(data["paths"]) == 4

    assert data["paths"][0]["station_sequence"] == ["A", "B", "C", "D"]
    assert data["paths"][0]["path_length"] == 4
    assert data["paths"][0]["traversal_count"] == 2

def test_api_station_pair_route_diversity_not_found(client: TestClient, route_diversity_fixtures: dict) -> None:
    res = client.get("/api/v1/network/stations/UNKNOWN/D/route-diversity")
    assert res.status_code == 404
