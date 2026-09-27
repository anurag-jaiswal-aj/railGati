from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.services.test_network_station_neighborhood_triadic_closure import setup_service_data, setup_zero_closure  # noqa: F401


def test_get_station_neighborhood_triadic_closure_success(client: TestClient, db_session: Session, setup_service_data):
    response = client.get("/api/v1/network/stations/S/neighborhood-triadic-closure")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "S"
    assert data["outbound_degree"] == 3
    assert data["possible_neighbor_pairs"] == 3
    assert data["closed_neighbor_pairs"] == 1
    assert data["triadic_closure_ratio"] == 1.0 / 3.0


def test_get_station_neighborhood_triadic_closure_zero(client: TestClient, db_session: Session, setup_zero_closure):
    response = client.get("/api/v1/network/stations/E/neighborhood-triadic-closure")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "E"
    assert data["outbound_degree"] == 3
    assert data["possible_neighbor_pairs"] == 3
    assert data["closed_neighbor_pairs"] == 0
    assert data["triadic_closure_ratio"] == 0.0


def test_get_station_neighborhood_triadic_closure_undefined(client: TestClient, db_session: Session, setup_service_data):
    response = client.get("/api/v1/network/stations/F/neighborhood-triadic-closure")
    assert response.status_code == 400
    assert "outbound_degree < 2" in response.json()["detail"]


def test_get_station_neighborhood_triadic_closure_unknown_station(client: TestClient, db_session: Session, setup_service_data):
    response = client.get("/api/v1/network/stations/UNKNOWN/neighborhood-triadic-closure")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_station_neighborhood_triadic_closure_no_snapshot(client: TestClient, db_session: Session):
    response = client.get("/api/v1/network/stations/S/neighborhood-triadic-closure")
    assert response.status_code == 503
    assert "no active snapshot" in response.json()["detail"].lower()
