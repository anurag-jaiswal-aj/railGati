import pytest
from starlette.testclient import TestClient

def test_api_assortativity_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_calc(db, snapshot_id, target_train_number):
        return {
            "train_number": target_train_number,
            "timetable_snapshot_id": snapshot_id,
            "route_assortativity_coefficient": 0.25,
            "distinct_route_edges": 10,
        }

    monkeypatch.setattr(
        "railgati.services.network.calculate_train_topological_global_degree_assortativity",
        mock_calc,
    )
    
    def mock_get_snapshot(db):
        return 1

    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id",
        mock_get_snapshot,
    )

    response = client.get("/api/v1/network/trains/12345/topological-global-degree-assortativity")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12345"
    assert data["route_assortativity_coefficient"] == 0.25
    assert data["distinct_route_edges"] == 10

def test_api_assortativity_not_found(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_calc(db, snapshot_id, target_train_number):
        raise ValueError(f"Train {target_train_number} not found")

    monkeypatch.setattr(
        "railgati.services.network.calculate_train_topological_global_degree_assortativity",
        mock_calc,
    )

    def mock_get_snapshot(db):
        return 1

    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id",
        mock_get_snapshot,
    )

    response = client.get("/api/v1/network/trains/99999/topological-global-degree-assortativity")
    assert response.status_code == 404
