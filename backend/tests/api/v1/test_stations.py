"""Tests for the Stations API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_search_stations_exact_code(client: TestClient, populated_db: Session) -> None:
    """Test exact code match gets ordered first."""
    response = client.get("/api/v1/stations/search?q=ndls")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] >= 1
    # NDLS should be first
    assert data["items"][0]["code"] == "NDLS"


def test_search_stations_name_match(client: TestClient, populated_db: Session) -> None:
    """Test name match."""
    response = client.get("/api/v1/stations/search?q=mumbai")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["code"] == "BCT"


def test_search_stations_pagination(client: TestClient, populated_db: Session) -> None:
    """Test pagination bounds."""
    response = client.get("/api/v1/stations/search?q=n&page=1&size=1")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert len(data["items"]) == 1


def test_search_stations_empty_query(client: TestClient, populated_db: Session) -> None:
    """Test empty query validation."""
    response = client.get("/api/v1/stations/search?q=")
    assert response.status_code == 422


def test_search_stations_excludes_failed_snapshots(
    client: TestClient, populated_db: Session
) -> None:
    """Test that FAIL code from FAILED snapshot is not returned."""
    response = client.get("/api/v1/stations/search?q=fail")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 0


def test_get_station_detail(client: TestClient, populated_db: Session) -> None:
    """Test canonical station detail."""
    response = client.get("/api/v1/stations/ndls")
    assert response.status_code == 200
    data = response.json()

    assert data["code"] == "NDLS"
    assert data["name"] == "New Delhi"
    assert data["provenance"]["snapshot_id"] is not None


def test_get_station_detail_not_found(client: TestClient, populated_db: Session) -> None:
    """Test non-existent station."""
    response = client.get("/api/v1/stations/UNKNOWN")
    assert response.status_code == 404


def test_get_station_trains_success(client: TestClient, populated_db: Session) -> None:
    """Test get historical trains for a station."""
    # Note: we need a timetable snapshot in populated_db for this to work
    # We will simulate this by manually adding a timetable snapshot and stops for NDLS in this test.
    from datetime import UTC, datetime

    from railgati.models.provenance import DatasetSnapshot, DataSource
    from railgati.models.station import Station
    from railgati.models.train import Train, TrainObservation, TrainStopObservation

    source = populated_db.query(DataSource).first()
    assert source is not None

    # 1. Timetable Snapshot
    tt_snap = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=2,
        status="ACTIVE",
    )
    populated_db.add(tt_snap)
    populated_db.commit()

    # 2. Trains
    t1 = Train(number="12952")
    t2 = Train(number="12951")
    populated_db.add_all([t1, t2])
    populated_db.commit()

    # 3. Train Observations
    tobs1 = TrainObservation(snapshot_id=tt_snap.id, train_id=t1.id, name="Mumbai Rajdhani")
    tobs2 = TrainObservation(snapshot_id=tt_snap.id, train_id=t2.id, name="Delhi Rajdhani")
    populated_db.add_all([tobs1, tobs2])

    # 4. Train Stops
    # Find NDLS station_id
    ndls_station = populated_db.query(Station).filter_by(code="NDLS").one()
    stop1 = TrainStopObservation(
        snapshot_id=tt_snap.id, train_id=t1.id, station_id=ndls_station.id, stop_sequence=1
    )

    # Add duplicate stop for the same train theoretically visiting
    # the station again to test deduplication
    stop1_dup = TrainStopObservation(
        snapshot_id=tt_snap.id, train_id=t1.id, station_id=ndls_station.id, stop_sequence=2
    )
    populated_db.add_all([stop1, stop1_dup])
    populated_db.commit()

    response = client.get("/api/v1/stations/ndls/trains")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["train_number"] == "12952"


def test_get_station_trains_not_found(client: TestClient, populated_db: Session) -> None:
    """Test get historical trains for unknown station."""
    response = client.get("/api/v1/stations/XYZ/trains")
    assert response.status_code == 404
