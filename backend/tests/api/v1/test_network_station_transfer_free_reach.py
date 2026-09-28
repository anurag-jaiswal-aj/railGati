import typing

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.services.test_network_station_transfer_free_reach import (
    tfr_fixtures as tfr_fixtures,
)


def test_tfr_api_success(
    client: TestClient, db_session: Session, tfr_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/S1/transfer-free-reach")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "S1"
    assert data["topological_outbound_degree"] == 2
    assert data["transfer_free_outbound_reach"] == 4
    assert data["reachability_span_ratio"] == 2.0

def test_tfr_not_found(
    client: TestClient, db_session: Session, tfr_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/UNKNOWN/transfer-free-reach")
    assert response.status_code == 404

def test_tfr_undefined_ratio(
    client: TestClient, db_session: Session, tfr_fixtures: typing.Any
) -> None:
    # S5 has no outbound. N1=0 -> ValueError -> 400 Bad Request
    response = client.get("/api/v1/network/stations/S5/transfer-free-reach")
    assert response.status_code == 400
    assert "undefined" in response.json()["detail"].lower()
