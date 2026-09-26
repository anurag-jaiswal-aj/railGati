"""Tests for the Trains API."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture(scope="function")
def train_db(db_session: Session) -> Session:
    """Provides a database populated with train timetable data."""
    # 1. Source
    source = DataSource(
        name="Timetable Source",
        publisher="Test Publisher",
        url="http://test.com",
        license="Test",
    )
    db_session.add(source)
    db_session.commit()

    # 2. Station Snapshot
    station_snap = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=2,
        status="ACTIVE",
    )
    db_session.add(station_snap)
    db_session.commit()

    # Stations
    s1 = Station(code="NDLS")
    s2 = Station(code="BCT")
    db_session.add_all([s1, s2])
    db_session.commit()

    obs1 = StationObservation(snapshot_id=station_snap.id, station_id=s1.id, name="New Delhi")
    obs2 = StationObservation(snapshot_id=station_snap.id, station_id=s2.id, name="Mumbai Central")
    db_session.add_all([obs1, obs2])

    # 3. Timetable Snapshot
    tt_snap = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=2,
        status="ACTIVE",
    )
    db_session.add(tt_snap)
    db_session.commit()

    # Trains
    t1 = Train(number="12952")
    t2 = Train(number="12952P")
    t3 = Train(number="12951")
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # Train Observations
    tobs1 = TrainObservation(
        snapshot_id=tt_snap.id,
        train_id=t1.id,
        name="Mumbai Rajdhani",
        type="Rajdhani",
        return_train_number="12951",
    )
    tobs2 = TrainObservation(
        snapshot_id=tt_snap.id,
        train_id=t2.id,
        name="Mumbai Rajdhani Premium",
        type="Premium",
        return_train_number=None,
    )
    tobs3 = TrainObservation(
        snapshot_id=tt_snap.id,
        train_id=t3.id,
        name="Delhi Rajdhani",
        type="Rajdhani",
        return_train_number="12952",
    )
    db_session.add_all([tobs1, tobs2, tobs3])

    # Stops for 12952
    stop1 = TrainStopObservation(
        snapshot_id=tt_snap.id,
        train_id=t1.id,
        station_id=s1.id,
        stop_sequence=1,
        departure_time="16:55:00",
        source_day=1,
    )
    stop2 = TrainStopObservation(
        snapshot_id=tt_snap.id,
        train_id=t1.id,
        station_id=s2.id,
        stop_sequence=2,
        arrival_time="08:35:00",
        source_day=2,
    )
    db_session.add_all([stop1, stop2])
    db_session.commit()

    # Add an old snapshot with a train that shouldn't be returned
    old_snap = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime(2020, 1, 1, tzinfo=UTC),
        record_count=1,
        status="ACTIVE",
    )
    db_session.add(old_snap)
    db_session.commit()

    t4 = Train(number="00000")
    db_session.add(t4)
    db_session.commit()

    tobs4 = TrainObservation(
        snapshot_id=old_snap.id,
        train_id=t4.id,
        name="Old Train",
        type="Old",
        return_train_number=None,
    )
    db_session.add(tobs4)
    db_session.commit()

    return db_session


def test_search_trains_exact_number(client: TestClient, train_db: Session) -> None:
    """Test exact train number match is returned first."""
    response = client.get("/api/v1/trains/search?q=12952")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["items"][0]["train_number"] == "12952"
    assert data["items"][1]["train_number"] == "12952P"


def test_search_trains_prefix_name(client: TestClient, train_db: Session) -> None:
    """Test train search by name."""
    response = client.get("/api/v1/trains/search?q=mumbai")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["items"][0]["name"].startswith("Mumbai")


def test_search_trains_without_q(client: TestClient, train_db: Session) -> None:
    """Test train search without query returns all active ordered."""
    response = client.get("/api/v1/trains/search")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    # Ordered by number ASC
    assert data["items"][0]["train_number"] == "12951"
    assert data["items"][1]["train_number"] == "12952"
    assert data["items"][2]["train_number"] == "12952P"


def test_search_trains_excludes_old_snapshot(client: TestClient, train_db: Session) -> None:
    """Test that train 00000 from old snapshot is not returned."""
    response = client.get("/api/v1/trains/search?q=00000")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


def test_search_trains_pagination(client: TestClient, train_db: Session) -> None:
    """Test pagination bounds."""
    response = client.get("/api/v1/trains/search?page=2&size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["items"][0]["train_number"] == "12952P"


def test_search_trains_invalid_pagination(client: TestClient, train_db: Session) -> None:
    """Test invalid pagination."""
    response = client.get("/api/v1/trains/search?page=0&size=10")
    assert response.status_code == 422


def test_get_train_detail(client: TestClient, train_db: Session) -> None:
    """Test canonical train detail."""
    response = client.get("/api/v1/trains/12952")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12952"
    assert data["name"] == "Mumbai Rajdhani"
    assert data["type"] == "Rajdhani"
    assert data["return_train_number"] == "12951"
    assert data["provenance"]["snapshot_id"] is not None


def test_get_train_detail_not_found(client: TestClient, train_db: Session) -> None:
    """Test train detail not found."""
    response = client.get("/api/v1/trains/99999")
    assert response.status_code == 404


def test_get_train_route(client: TestClient, train_db: Session) -> None:
    """Test canonical train route with canonical station information."""
    response = client.get("/api/v1/trains/12952/route")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    stop1 = data[0]
    assert stop1["stop_sequence"] == 1
    assert stop1["station_code"] == "NDLS"
    assert stop1["station_name"] == "New Delhi"
    assert stop1["arrival_time"] is None
    assert stop1["departure_time"] == "16:55:00"
    assert stop1["source_day"] == 1

    stop2 = data[1]
    assert stop2["stop_sequence"] == 2
    assert stop2["station_code"] == "BCT"
    assert stop2["station_name"] == "Mumbai Central"
    assert stop2["arrival_time"] == "08:35:00"
    assert stop2["departure_time"] is None
    assert stop2["source_day"] == 2


def test_search_trains_between_unavailable(client: TestClient) -> None:
    """Test train discovery returns 501 Not Implemented with graceful message."""
    response = client.get("/api/v1/trains/between?source=NDLS&destination=BCT")
    assert response.status_code == 501
    data = response.json()
    assert data["available"] is False
    assert "unavailable" in data["message"].lower()
