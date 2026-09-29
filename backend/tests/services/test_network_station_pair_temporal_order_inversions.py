import pytest
from sqlalchemy.orm import Session
from railgati.services.network import calculate_station_pair_temporal_order_inversions
from railgati.models.station import Station
from railgati.models.train import Train, TrainStopObservation
from railgati.models.provenance import DatasetSnapshot, DataSource

def setup_mock_inversions(db_session: Session) -> tuple[str, str, int]:
    # Ensure source/snapshot exists
    source = db_session.query(DataSource).first()
    if not source:
        source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
        db_session.add(source)
        db_session.commit()
        
    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    # Create O and D stations
    o = Station(code="MOCK_O")
    d = Station(code="MOCK_D")
    db_session.add_all([o, d])
    db_session.commit()

    # Create 3 trains
    t1 = Train(number="1001")
    t2 = Train(number="1002")
    t3 = Train(number="1003")
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

    # Train 3: departs 10:30, arrives 12:30 (No inversion with Train 2 because same departure time. No inversion with Train 1 because departs later and arrives later.)
    db_session.add(TrainStopObservation(
        snapshot_id=snap_id, train_id=t3.id, station_id=o.id,
        stop_sequence=1, departure_time="10:30:00", source_day=1
    ))
    db_session.add(TrainStopObservation(
        snapshot_id=snap_id, train_id=t3.id, station_id=d.id,
        stop_sequence=2, arrival_time="12:30:00", source_day=1
    ))

    db_session.commit()
    return "MOCK_O", "MOCK_D", snap_id


def test_service_temporal_inversion_mock_data(db_session: Session):
    o_code, d_code, snap_id = setup_mock_inversions(db_session)
    result = calculate_station_pair_temporal_order_inversions(
        db_session, o_code, d_code, snap_id
    )
    
    assert result["origin_station_code"] == o_code
    assert result["destination_station_code"] == d_code
    assert result["total_valid_traversal_count"] == 3
    # Only Train 1 and Train 2 form an inversion pair
    assert result["inversion_pair_count"] == 1
    assert result["distinct_inverted_train_count"] == 2

def test_service_temporal_inversion_zero_traversals(db_session: Session):
    o = Station(code="ZERO_O")
    d = Station(code="ZERO_D")
    db_session.add_all([o, d])
    db_session.commit()
    
    result = calculate_station_pair_temporal_order_inversions(
        db_session, "ZERO_O", "ZERO_D", 1
    )
    assert result["total_valid_traversal_count"] == 0
    assert result["inversion_pair_count"] == 0
    assert result["distinct_inverted_train_count"] == 0

def test_service_temporal_inversion_invalid_origin_dest(db_session: Session):
    with pytest.raises(ValueError, match="cannot be identical"):
        calculate_station_pair_temporal_order_inversions(db_session, "CNB", "CNB", 1)
