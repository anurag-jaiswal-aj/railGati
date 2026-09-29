import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from railgati.models.station import Station
from railgati.models.train import Train, TrainStopObservation, TrainObservation
from railgati.models.provenance import DatasetSnapshot, DataSource

def setup_mock_inversions_api(db_session: Session) -> tuple[str, str]:
    # Ensure source/snapshot exists
    source = db_session.query(DataSource).first()
    if not source:
        source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
        db_session.add(source)
        db_session.commit()
        
    snap = db_session.query(DatasetSnapshot).first()
    if not snap:
        snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
        db_session.add(snap)
        db_session.commit()
    snap.status = "ACTIVE"
    db_session.commit()
    snap_id = snap.id

    # Add a TrainObservation to satisfy get_active_timetable_snapshot_id
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=1, name="dummy"))
    db_session.commit()

    # Create O, D, and NDLS stations
    o = Station(code="MOCKO")
    d = Station(code="MOCKD")
    ndls = Station(code="NDLS")
    db_session.add_all([o, d, ndls])
    db_session.commit()

    # Create 3 trains
    t1 = Train(number="2001")
    t2 = Train(number="2002")
    t3 = Train(number="2003")
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # Train 1: departs 10:00, arrives 12:00
    db_session.add(TrainStopObservation(
        snapshot_id=snap_id, train_id=t1.id, station_id=o.id,
        stop_sequence=1, departure_time="10:00:00", source_day=1
    ))
    db_session.add(TrainStopObservation(
        snapshot_id=snap_id, train_id=t1.id, station_id=d.id,
        stop_sequence=2, arrival_time="12:00:00", source_day=1
    ))

    # Train 2: departs 10:30, arrives 11:30 (Inverts with Train 1! Departs later, arrives earlier)
    db_session.add(TrainStopObservation(
        snapshot_id=snap_id, train_id=t2.id, station_id=o.id,
        stop_sequence=1, departure_time="10:30:00", source_day=1
    ))
    db_session.add(TrainStopObservation(
        snapshot_id=snap_id, train_id=t2.id, station_id=d.id,
        stop_sequence=2, arrival_time="11:30:00", source_day=1
    ))

    db_session.commit()
    return "MOCKO", "MOCKD"

def test_api_temporal_inversion_success(client: TestClient, db_session: Session):
    """Test valid distinct inversion API response."""
    o, d = setup_mock_inversions_api(db_session)
    response = client.get(f"/api/v1/network/station-pairs/{o}/{d}/temporal-order-inversions")
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["origin_station_code"] == o
    assert data["destination_station_code"] == d
    assert "timetable_snapshot_id" in data
    assert data["total_valid_traversal_count"] == 2
    assert data["inversion_pair_count"] == 1
    assert data["distinct_inverted_train_count"] == 2

def test_api_temporal_inversion_missing_origin(client: TestClient, db_session: Session):
    """Test API response for missing origin station."""
    setup_mock_inversions_api(db_session)
    response = client.get("/api/v1/network/station-pairs/INVALID/MOCKD/temporal-order-inversions")
    assert response.status_code == 404

def test_api_temporal_inversion_missing_dest(client: TestClient, db_session: Session):
    """Test API response for missing destination station."""
    setup_mock_inversions_api(db_session)
    response = client.get("/api/v1/network/station-pairs/MOCKO/INVALID/temporal-order-inversions")
    assert response.status_code == 404

def test_api_temporal_inversion_same_stations(client: TestClient, db_session: Session):
    """Test API response for identical origin and destination."""
    setup_mock_inversions_api(db_session)
    response = client.get("/api/v1/network/station-pairs/MOCKO/MOCKO/temporal-order-inversions")
    assert response.status_code == 400
    assert "cannot be identical" in response.json()["detail"].lower()

def test_api_temporal_inversion_zero_results(client: TestClient, db_session: Session):
    """Test API response for stations with no connectivity."""
    setup_mock_inversions_api(db_session)
    response = client.get("/api/v1/network/station-pairs/NDLS/MOCKD/temporal-order-inversions")
    assert response.status_code == 200
    data = response.json()
    assert data["total_valid_traversal_count"] == 0
    assert data["inversion_pair_count"] == 0
    assert data["distinct_inverted_train_count"] == 0
