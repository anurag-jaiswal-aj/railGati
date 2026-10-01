import pytes
from starlette.testclient import TestClien

def test_api_structural_gradient_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_calc(db, snapshot_id, target_train_number):
        return {
            "train_number": target_train_number,
            "timetable_snapshot_id": snapshot_id,
            "topological_structural_gradient_tau": -0.85,
            "total_sequence_stops": 20,
        }

    monkeypatch.setattr(
        "railgati.services.network.calculate_train_topological_structural_gradient",
        mock_calc,
    )

    def mock_get_snapshot(db):
        return 1

    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id",
        mock_get_snapshot,
    )

    response = client.get("/api/v1/network/trains/12345/topological-structural-gradient")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12345"
    assert data["topological_structural_gradient_tau"] == -0.85
    assert data["total_sequence_stops"] == 20

def test_api_structural_gradient_not_found(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_calc(db, snapshot_id, target_train_number):
        raise ValueError(f"Train {target_train_number} not found")

    monkeypatch.setattr(
        "railgati.services.network.calculate_train_topological_structural_gradient",
        mock_calc,
    )

    def mock_get_snapshot(db):
        return 1

    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id",
        mock_get_snapshot,
    )

    response = client.get("/api/v1/network/trains/99999/topological-structural-gradient")
    assert response.status_code == 404
