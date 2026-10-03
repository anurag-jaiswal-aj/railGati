import pytest
from fastapi.testclient import TestClient

from tests.services.test_network_edge_topological_bridge_bipartition_size import bridge_fixtures, test_snapshot_id


@pytest.fixture(autouse=True)
def mock_snapshot_id(monkeypatch: pytest.MonkeyPatch, bridge_fixtures: int) -> None:
    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id", lambda _: bridge_fixtures
    )


def test_bridge_bipartition_size_endpoint_success(
    client: TestClient, bridge_fixtures: int
) -> None:
    response = client.get("/api/v1/network/edges/S_A/S_B/topological-bridge-bipartition-size")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "S_A"
    assert data["to_station_code"] == "S_B"
    assert data["timetable_snapshot_id"] == bridge_fixtures
    assert data["is_bridge"] is True
    assert data["bridge_bipartition_size"] == 1


def test_bridge_bipartition_size_non_bridge(
    client: TestClient, bridge_fixtures: int
) -> None:
    response = client.get("/api/v1/network/edges/C1/C2/topological-bridge-bipartition-size")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "C1"
    assert data["to_station_code"] == "C2"
    assert data["is_bridge"] is False
    assert data["bridge_bipartition_size"] == 0


def test_bridge_bipartition_size_reverse(
    client: TestClient, bridge_fixtures: int
) -> None:
    response = client.get("/api/v1/network/edges/S_B/S_A/topological-bridge-bipartition-size")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "S_B"
    assert data["to_station_code"] == "S_A"
    assert data["is_bridge"] is True
    assert data["bridge_bipartition_size"] == 1


def test_bridge_bipartition_size_unknown_station(
    client: TestClient, bridge_fixtures: int
) -> None:
    response = client.get("/api/v1/network/edges/UNKNOWN/S_A/topological-bridge-bipartition-size")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_bridge_bipartition_size_missing_edge(
    client: TestClient, bridge_fixtures: int
) -> None:
    response = client.get("/api/v1/network/edges/S_A/C1/topological-bridge-bipartition-size")
    assert response.status_code == 404
    assert "not found in the active graph" in response.json()["detail"].lower()


def test_bridge_bipartition_size_self_loop(
    client: TestClient, bridge_fixtures: int
) -> None:
    response = client.get("/api/v1/network/edges/S_A/S_A/topological-bridge-bipartition-size")
    assert response.status_code == 400
    assert "self-loops are excluded" in response.json()["detail"].lower()
