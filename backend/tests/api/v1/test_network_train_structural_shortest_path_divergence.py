import pytest
from fastapi.testclient import TestClient

def test_api_shortest_path_divergence_success(client: TestClient, db_session, monkeypatch) -> None:
    def mock_calc(db, snap_id, train_no):
        return {
            "train_number": "T1",
            "timetable_snapshot_id": 2,
            "start_station_code": "A",
            "end_station_code": "B",
            "actual_structural_edges": 3,
            "shortest_structural_edges": 1,
            "divergence_absolute": 2,
            "divergence_ratio": 3.0
        }
    monkeypatch.setattr(
        "railgati.services.network.calculate_train_structural_shortest_path_divergence", mock_calc
    )
    monkeypatch.setattr(
        "railgati.api.v1.snapshots.get_active_timetable_snapshot_id", lambda x: 2
    )

    response = client.get("/api/v1/network/trains/T1/structural-shortest-path-divergence")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "T1"
    assert data["divergence_absolute"] == 2
    assert data["divergence_ratio"] == 3.0


def test_api_shortest_path_divergence_not_found(client: TestClient, db_session, monkeypatch) -> None:
    def mock_calc(db, snap_id, train_no):
        raise ValueError(f"Train '{train_no}' not found")

    monkeypatch.setattr(
        "railgati.services.network.calculate_train_structural_shortest_path_divergence", mock_calc
    )
    monkeypatch.setattr(
        "railgati.api.v1.snapshots.get_active_timetable_snapshot_id", lambda x: 2
    )

    response = client.get("/api/v1/network/trains/UNKNOWN/structural-shortest-path-divergence")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
