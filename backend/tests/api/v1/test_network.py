"""Tests for the Network Reachability API endpoint."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station


@pytest.fixture
def network_api_data(db_session: Session) -> dict[str, Any]:
    """Setup minimal data for network API testing."""
    # Source
    src = DataSource(
        name="Test API Network Source",
        publisher="test publisher",
        url="http://test",
        license="MIT",
    )
    db_session.add(src)
    db_session.commit()

    # Active timetable snapshot
    snap_active = DatasetSnapshot(
        source_id=src.id,
        status="ACTIVE",
    )
    db_session.add(snap_active)
    db_session.commit()

    from railgati.models.train import Train, TrainObservation

    dummy_train = Train(number="000")
    db_session.add(dummy_train)
    db_session.commit()

    dummy_obs = TrainObservation(
        snapshot_id=snap_active.id,
        train_id=dummy_train.id,
        name="Dummy",
    )
    db_session.add(dummy_obs)
    db_session.commit()

    # Create stations
    org = Station(code="API_ORG")
    dst1 = Station(code="API_DST1")
    dst2 = Station(code="API_DST2")
    db_session.add_all([org, dst1, dst2])
    db_session.commit()

    # Active station snapshot
    from railgati.models.station import StationObservation

    snap_station = DatasetSnapshot(
        source_id=src.id,
        status="ACTIVE",
    )
    db_session.add(snap_station)
    db_session.commit()

    obs_org = StationObservation(
        snapshot_id=snap_station.id, station_id=org.id, name="Origin Station"
    )
    obs_dst1 = StationObservation(
        snapshot_id=snap_station.id, station_id=dst1.id, name="Destination One"
    )
    # intentionally leave dst2 without observation to test missing metadata
    db_session.add_all([obs_org, obs_dst1])
    db_session.commit()

    return {
        "org_code": org.code,
        "snap_id": snap_active.id,
    }


def test_get_reachable_stations_success(
    client: TestClient, network_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test successful network reachability."""

    # Mock the service to return dummy data
    from railgati.services.network import StationReachability

    def mock_find(*args: Any, **kwargs: Any) -> list[StationReachability]:
        return [
            StationReachability(
                station_id=2,  # Should map to API_DST1
                min_hops=1,
            ),
            StationReachability(
                station_id=3,  # Should map to API_DST2 (which has no name)
                min_hops=2,
            ),
        ]

    monkeypatch.setattr("railgati.api.v1.network.find_reachable_stations", mock_find)

    response = client.get(f"/api/v1/network/reachable?origin={network_api_data['org_code']}")
    assert response.status_code == 200
    data = response.json()

    assert data["origin"] == network_api_data["org_code"]
    assert data["timetable_snapshot_id"] == network_api_data["snap_id"]
    assert data["max_hops"] == 3  # default
    assert data["total"] == 2
    assert len(data["stations"]) == 2

    dest1 = data["stations"][0]
    assert dest1["station_code"] == "API_DST1"
    assert dest1["station_name"] == "Destination One"
    assert dest1["min_hops"] == 1

    dest2 = data["stations"][1]
    assert dest2["station_code"] == "API_DST2"
    assert dest2["station_name"] is None
    assert dest2["min_hops"] == 2


def test_get_reachable_stations_unknown_origin(client: TestClient) -> None:
    """Test 404 for unknown origin station."""
    response = client.get("/api/v1/network/reachable?origin=UNKNOWN_XXX")
    assert response.status_code == 404
    assert "UNKNOWN_XXX" in response.json()["detail"]


def test_get_reachable_stations_no_results(
    client: TestClient, network_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 200 with empty array when no reachable stations found."""
    monkeypatch.setattr(
        "railgati.api.v1.network.find_reachable_stations", lambda *args, **kwargs: []
    )
    response = client.get(f"/api/v1/network/reachable?origin={network_api_data['org_code']}")
    assert response.status_code == 200
    data = response.json()
    assert data["stations"] == []
    assert data["total"] == 0


def test_get_reachable_stations_max_hops(
    client: TestClient, network_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test pass-through of max_hops."""

    captured_kwargs: dict[str, Any] = {}

    def mock_find(*args: Any, **kwargs: Any) -> list[Any]:
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr("railgati.api.v1.network.find_reachable_stations", mock_find)

    response = client.get(
        f"/api/v1/network/reachable?origin={network_api_data['org_code']}&max_hops=10"
    )
    assert response.status_code == 200
    assert captured_kwargs["max_hops"] == 10
    data = response.json()
    assert data["max_hops"] == 10


def test_get_reachable_stations_invalid_max_hops(
    client: TestClient, network_api_data: dict[str, Any]
) -> None:
    """Test 422 for max_hops out of bounds or invalid."""
    response = client.get(
        f"/api/v1/network/reachable?origin={network_api_data['org_code']}&max_hops=0"
    )
    assert response.status_code == 422

    response = client.get(
        f"/api/v1/network/reachable?origin={network_api_data['org_code']}&max_hops=11"
    )
    assert response.status_code == 422

    response = client.get(
        f"/api/v1/network/reachable?origin={network_api_data['org_code']}&max_hops=-1"
    )
    assert response.status_code == 422

    response = client.get(
        f"/api/v1/network/reachable?origin={network_api_data['org_code']}&max_hops=abc"
    )
    assert response.status_code == 422


def test_get_reachable_stations_no_active_snapshot(client: TestClient, db_session: Session) -> None:
    """Test 503 when no active timetable snapshot exists."""
    db_session.query(DatasetSnapshot).delete()
    org = Station(code="LONE")
    db_session.add(org)
    db_session.commit()

    response = client.get("/api/v1/network/reachable?origin=LONE")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_get_reachable_stations_missing_graph_build(
    client: TestClient, network_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 503 when graph build is unavailable (service raises ValueError)."""

    def mock_find_raises(*args: Any, **kwargs: Any) -> list[Any]:
        raise ValueError("Active graph build unavailable for this snapshot")

    monkeypatch.setattr("railgati.api.v1.network.find_reachable_stations", mock_find_raises)

    response = client.get(f"/api/v1/network/reachable?origin={network_api_data['org_code']}")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_case_insensitive_origin(
    client: TestClient, network_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test origin lookup is case insensitive."""
    monkeypatch.setattr(
        "railgati.api.v1.network.find_reachable_stations", lambda *args, **kwargs: []
    )
    lower_code = network_api_data["org_code"].lower()
    response = client.get(f"/api/v1/network/reachable?origin={lower_code}")
    assert response.status_code == 200
    assert response.json()["origin"] == network_api_data["org_code"]  # Should return canonical
