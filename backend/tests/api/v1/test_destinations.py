"""Tests for the Destinations API endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from typing import Any
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station


@pytest.fixture
def destinations_data(db_session: Session) -> dict[str, Any]:
    """Setup minimal data for destination API testing."""
    # Source
    src = DataSource(
        name="Test API Destination Source",
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

    # We must add at least one TrainObservation so that the snapshot
    # is identified as a timetable snapshot by get_active_timetable_snapshot_id
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
    db_session.add_all([org, dst1])
    db_session.commit()

    # Note: We do not insert actual TrainStopObservation here to avoid duplicating
    # the complex service setup logic. For simple API tests, we can either mock
    # the service or rely on the fact that an empty DB returns []
    # and testing the integration with `find_direct_destinations` can just ensure 200 OK.
    # We will use monkeypatch to mock the service layer to precisely test the API contract.
    return {
        "org_code": org.code,
        "snap_id": snap_active.id,
    }


def test_get_destinations_success(
    client: TestClient, destinations_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test successful destination discovery."""

    # Mock the service to return dummy data
    from railgati.api.v1.schemas import TimingConfidence
    from railgati.services.destination import DirectDestinationResult

    def mock_find(*args: Any, **kwargs: Any) -> list[DirectDestinationResult]:
        return [
            DirectDestinationResult(
                station_id=2,
                station_code="API_DST1",
                fastest_duration_minutes=120,
                direct_trains_count=2,
                timing_confidence=TimingConfidence.HIGH,
            )
        ]

    monkeypatch.setattr("railgati.api.v1.destinations.find_direct_destinations", mock_find)

    response = client.get(f"/api/v1/destinations?origin={destinations_data['org_code']}")
    assert response.status_code == 200
    data = response.json()

    assert data["origin"] == destinations_data["org_code"]
    assert data["timetable_snapshot_id"] == destinations_data["snap_id"]
    assert data["max_duration_minutes"] is None
    assert len(data["destinations"]) == 1

    dest = data["destinations"][0]
    assert dest["station_code"] == "API_DST1"
    assert dest["fastest_duration_minutes"] == 120
    assert dest["direct_train_count"] == 2
    assert dest["timing_confidence"] == "HIGH"


def test_get_destinations_unknown_origin(client: TestClient) -> None:
    """Test 404 for unknown origin station."""
    response = client.get("/api/v1/destinations?origin=UNKNOWN_XXX")
    assert response.status_code == 404
    assert "UNKNOWN_XXX" in response.json()["detail"]


def test_get_destinations_no_results(
    client: TestClient, destinations_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 200 with empty array when no destinations found."""
    monkeypatch.setattr(
        "railgati.api.v1.destinations.find_direct_destinations", lambda *args, **kwargs: []
    )
    response = client.get(f"/api/v1/destinations?origin={destinations_data['org_code']}")
    assert response.status_code == 200
    data = response.json()
    assert data["destinations"] == []


def test_get_destinations_max_duration(
    client: TestClient, destinations_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test pass-through of max_duration_minutes."""

    captured_kwargs: dict[str, Any] = {}

    def mock_find(*args: Any, **kwargs: Any) -> list[Any]:
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr("railgati.api.v1.destinations.find_direct_destinations", mock_find)

    response = client.get(
        f"/api/v1/destinations?origin={destinations_data['org_code']}&max_duration_minutes=300"
    )
    assert response.status_code == 200
    assert captured_kwargs["max_duration_minutes"] == 300
    data = response.json()
    assert data["max_duration_minutes"] == 300


def test_get_destinations_negative_max_duration(
    client: TestClient, destinations_data: dict[str, Any]
) -> None:
    """Test 422 for negative max duration."""
    response = client.get(
        f"/api/v1/destinations?origin={destinations_data['org_code']}&max_duration_minutes=-10"
    )
    assert response.status_code == 422


def test_get_destinations_invalid_max_duration_type(
    client: TestClient, destinations_data: dict[str, Any]
) -> None:
    """Test 422 for invalid type for max duration."""
    response = client.get(
        f"/api/v1/destinations?origin={destinations_data['org_code']}&max_duration_minutes=abc"
    )
    assert response.status_code == 422


def test_get_destinations_no_active_snapshot(client: TestClient, db_session: Session) -> None:
    """Test 404 when no active timetable snapshot exists."""
    # Make sure we have a station but no snapshots
    db_session.query(DatasetSnapshot).delete()
    org = Station(code="LONE")
    db_session.add(org)
    db_session.commit()

    response = client.get("/api/v1/destinations?origin=LONE")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
