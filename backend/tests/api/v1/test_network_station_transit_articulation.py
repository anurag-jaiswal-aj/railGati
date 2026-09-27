import typing
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.services.test_network_station_transit_articulation import (
    setup_service_data,  # noqa: F401, F811
)


def test_get_station_transit_articulation_success(client: TestClient, db_session: Session, setup_service_data: typing.Any) -> None:
    response = client.get("/api/v1/network/stations/S/transit-articulation")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "S"
    assert data["inbound_degree"] == 3
    assert data["outbound_degree"] == 3
    assert data["transit_pairs_count"] == 8
    assert data["articulation_pairs_count"] == 6
    assert data["articulation_ratio"] == 0.75


def test_get_station_transit_articulation_zero_pairs(client: TestClient, db_session: Session, setup_service_data: typing.Any) -> None:
    response = client.get("/api/v1/network/stations/E/transit-articulation")
    assert response.status_code == 400


def test_get_station_transit_articulation_unknown_station(client: TestClient, db_session: Session, setup_service_data: typing.Any) -> None:
    response = client.get("/api/v1/network/stations/UNKNOWN/transit-articulation")
    assert response.status_code == 404


def test_get_station_transit_articulation_no_snapshot(client: TestClient, db_session: Session) -> None:
    response = client.get("/api/v1/network/stations/S/transit-articulation")
    assert response.status_code == 503
