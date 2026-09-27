import typing

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.services.test_network_station_reachability_expansion import (
    expansion_fixtures,  # noqa: F401, F811
)


def test_get_station_reachability_expansion_api_success(
    client: TestClient, db_session: Session, expansion_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/S1/2-hop-expansion")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "S1"
    assert data["n1_count"] == 1
    assert data["n2_count"] == 1
    assert data["expansion_ratio"] == 1.0


def test_get_station_reachability_expansion_not_found(
    client: TestClient, db_session: Session, expansion_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/UNKNOWN/2-hop-expansion")
    assert response.status_code == 404


def test_get_station_reachability_expansion_undefined(
    client: TestClient, db_session: Session, expansion_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/S9/2-hop-expansion")
    assert response.status_code == 400


def test_get_station_reachability_expansion_no_active_snapshot(
    client: TestClient, db_session: Session
) -> None:
    response = client.get("/api/v1/network/stations/S1/2-hop-expansion")
    assert response.status_code == 503
