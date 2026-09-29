from fastapi.testclient import TestClient
from tests.services.test_network_train_disjoint_subpath_reconvergences import mock_disjoint_reconvergences_data

def test_api_get_train_sequence_disjoint_subpath_reconvergences_success(
    client: TestClient, mock_disjoint_reconvergences_data
):
    response = client.get("/api/v1/network/trains/TARGET/disjoint-subpath-reconvergences")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "TARGET"
    assert data["total_reconvergence_count"] == 2
    assert len(data["reconvergences"]) == 2
    
    r = next(r for r in data["reconvergences"] if r["candidate_train_number"] == "CAND1")
    assert r["anchor_from_station_code"] == "STN_A"
    assert r["anchor_to_station_code"] == "STN_B"
    assert r["candidate_train_number"] == "CAND1"
    assert r["shared_interior_station_count"] == 0
    assert r["target_interior_station_count"] == 2
    assert r["candidate_interior_station_count"] == 2

def test_api_get_train_sequence_disjoint_subpath_reconvergences_not_found(
    client: TestClient, mock_disjoint_reconvergences_data
):
    response = client.get("/api/v1/network/trains/INVALID/disjoint-subpath-reconvergences")
    assert response.status_code == 404
