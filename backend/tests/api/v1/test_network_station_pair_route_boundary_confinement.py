import typing

from fastapi.testclient import TestClient


def test_api_get_station_pair_route_boundary_confinement_success(
    client: TestClient, route_diversity_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/A/D/route-boundary-confinement")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "D"
    assert data["total_traversal_count"] == 6
    assert data["strictly_bounded_count"] == 5
    assert data["destination_bounded_count"] == 1
    assert data["origin_bounded_count"] == 0
    assert data["unbounded_embedded_count"] == 0


def test_api_get_station_pair_route_boundary_confinement_empty(
    client: TestClient, route_diversity_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/D/A/route-boundary-confinement")
    assert response.status_code == 200
    data = response.json()
    assert data["total_traversal_count"] == 0


def test_api_get_station_pair_route_boundary_confinement_invalid_station(
    client: TestClient, route_diversity_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/UNKNOWN/D/route-boundary-confinement")
    assert response.status_code == 404
