import pytest
from sqlalchemy.orm import Session

from railgati.services.network import calculate_train_topology_loops
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainStopObservation

def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_svc", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_orig = Station(code="ORG")
    s_mid1 = Station(code="MD1")
    s_mid2 = Station(code="MD2")
    db_session.add_all([s_orig, s_mid1, s_mid2])
    db_session.flush()

    t_loop = Train(number="12345")
    t_linear = Train(number="54321")
    db_session.add_all([t_loop, t_linear])
    db_session.flush()

    from railgati.models.train import TrainObservation
    db_session.add_all([TrainObservation(snapshot_id=1, train_id=t_loop.id, name="Test1"), TrainObservation(snapshot_id=1, train_id=t_linear.id, name="Test2")])
    db_session.flush()

    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=3, station_id=s_mid2.id, arrival_time="12:00:00", departure_time="12:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=4, station_id=s_mid1.id, arrival_time="13:00:00", departure_time="13:10:00", source_day=1),
            
            TrainStopObservation(snapshot_id=1, train_id=t_linear.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_linear.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:10:00", source_day=1),
        ]
    )

    db_session.commit()

def test_service_topology_loops_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_train_topology_loops(db_session, 1, "12345")
    assert result["train_number"] == "12345"
    assert result["has_loops"] is True
    assert result["loop_count"] == 1
    
    md1_loop = result["loops"][0]
    assert md1_loop["station_code"] == "MD1"
    assert md1_loop["visit_count"] == 2
    assert md1_loop["max_sequence_span"] == 2

def test_service_topology_loops_linear(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_train_topology_loops(db_session, 1, "54321")
    assert result["train_number"] == "54321"
    assert result["has_loops"] is False
    assert result["loop_count"] == 0
    assert result["loops"] == []

def test_service_topology_loops_unknown_train(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_train_topology_loops(db_session, 1, "99999")

def test_service_topology_loops_archived(db_session: Session) -> None:
    setup_data(db_session)
    snapshot = db_session.get(DatasetSnapshot, 1)
    snapshot.status = "ARCHIVED"
    db_session.commit()
    
    with pytest.raises(RuntimeError, match="archived"):
        calculate_train_topology_loops(db_session, 1, "12345")
