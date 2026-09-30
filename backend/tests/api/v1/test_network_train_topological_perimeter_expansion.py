import pytest
from fastapi.testclient import TestClient

from tests.services.test_network_train_topological_perimeter_expansion import mock_perimeter_data

def test_api_train_perimeter_success(client: TestClient, mock_perimeter_data: dict) -> None:
    snap_id = mock_perimeter_data["snap_id"]
    response = client.get(
        "/api/v1/network/trains/T1/topological-perimeter-expansion",
        params={"snapshot_id": snap_id}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_train_number"] == "T1"
    assert data["route_station_count"] == 4
    assert data["perimeter_station_count"] == 5
    assert data["perimeter_expansion_ratio"] == 1.25
    
    codes = [s["station_code"] for s in data["perimeter_stations"]]
    assert codes == ["MULTIPLE_IN", "W", "X", "Y", "Z"]

def test_api_train_perimeter_unknown(client: TestClient, mock_perimeter_data: dict) -> None:
    snap_id = mock_perimeter_data["snap_id"]
    response = client.get(
        "/api/v1/network/trains/UNKNOWN/topological-perimeter-expansion",
        params={"snapshot_id": snap_id}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
