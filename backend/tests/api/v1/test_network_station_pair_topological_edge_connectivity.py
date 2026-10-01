from fastapi.testclient import TestClient
from tests.services.test_network_station_pair_topological_edge_connectivity import create_network, test_snapshot_id
import typing

def test_api_success_connected(client: TestClient, db_session: typing.Any, test_snapshot_id: int) -> None:
    create_network(db_session, test_snapshot_id, [(1,2)])
    response = client.get("/api/v1/network/station-pairs/ST1/ST2/topological-edge-connectivity")
    assert response.status_code == 200
    data = response.json()
    assert data["origin_station_code"] == "ST1"
    assert data["destination_station_code"] == "ST2"
    assert data["topological_edge_connectivity"] == 1

def test_api_success_same_station(client: TestClient, db_session: typing.Any, test_snapshot_id: int) -> None:
    create_network(db_session, test_snapshot_id, [(1,2)])
    response = client.get("/api/v1/network/station-pairs/ST1/ST1/topological-edge-connectivity")
    assert response.status_code == 200
    data = response.json()
    assert data["origin_station_code"] == "ST1"
    assert data["destination_station_code"] == "ST1"
    assert data["topological_edge_connectivity"] is None

def test_api_missing_origin(client: TestClient, db_session: typing.Any, test_snapshot_id: int) -> None:
    create_network(db_session, test_snapshot_id, [(1,2)])
    response = client.get("/api/v1/network/station-pairs/ST99/ST2/topological-edge-connectivity")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_missing_destination(client: TestClient, db_session: typing.Any, test_snapshot_id: int) -> None:
    create_network(db_session, test_snapshot_id, [(1,2)])
    response = client.get("/api/v1/network/station-pairs/ST1/ST99/topological-edge-connectivity")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
