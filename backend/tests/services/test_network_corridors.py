import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from railgati.main import app

from railgati.models.graph import RailwayGraphBuild
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import find_network_corridors

def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()
    return source

def setup_basic_graph(db_session: Session, source_id: int, snapshot_id: int = 1) -> None:
    snap = DatasetSnapshot(id=snapshot_id, source_id=source_id, status="ACTIVE")
    db_session.add(snap)
    gb = RailwayGraphBuild(timetable_snapshot_id=snapshot_id, status="ACTIVE")
    db_session.add(gb)
    
    # Station snapshot
    snap2 = DatasetSnapshot(id=snapshot_id + 100, source_id=source_id, status="ACTIVE")
    db_session.add(snap2)
    db_session.flush()

def test_one_train_one_occurrence(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    setup_basic_graph(db_session, source.id)

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()

    ts1 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1)
    ts2 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", departure_time="11:10", source_day=1)
    ts3 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id, arrival_time="12:00", source_day=1)
    db_session.add_all([ts1, ts2, ts3])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s3.id)
    assert len(res) == 1
    assert res[0].path == ["A", "B", "C"]
    assert res[0].occurrence_count == 1
    assert res[0].fastest_duration_minutes == 120

def test_one_train_multiple_valid_pairs(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    setup_basic_graph(db_session, source.id)

    t1 = Train(number="LOOP")
    db_session.add(t1)
    db_session.flush()

    # Occurrence 1
    ts1 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1)
    ts2 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", source_day=1)
    
    # Occurrence 2
    ts3 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s1.id, departure_time="13:00", source_day=1)
    ts4 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=4, station_id=s2.id, arrival_time="14:00", source_day=1)
    
    db_session.add_all([ts1, ts2, ts3, ts4])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res) == 2
    assert res[0].path == ["A", "B"]
    assert res[0].occurrence_count == 2
    assert res[1].path == ["A", "B", "A", "B"]
    assert res[1].occurrence_count == 1
    assert res[0].fastest_duration_minutes == 60

def test_two_trains_identical_corridor(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1")
    t2 = Train(number="T2")
    db_session.add_all([t1, t2])
    db_session.flush()

    ts1 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1)
    ts2 = TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", source_day=1)
    
    ts3 = TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id, departure_time="13:00", source_day=1)
    ts4 = TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s2.id, arrival_time="14:30", source_day=1)
    
    db_session.add_all([ts1, ts2, ts3, ts4])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res) == 1
    assert res[0].path == ["A", "B"]
    assert res[0].occurrence_count == 2
    assert res[0].fastest_duration_minutes == 60
def test_two_trains_different_corridors(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1") # A -> B -> D
    t2 = Train(number="T2") # A -> C -> D
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", departure_time="11:10", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s4.id, arrival_time="12:00", source_day=1),
        
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s3.id, arrival_time="11:00", departure_time="11:10", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=3, station_id=s4.id, arrival_time="13:00", source_day=1),
    ])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s4.id)
    assert len(res) == 2
    # Ensure they are sorted properly
    # count is 1 for both. fastest duration for T1 is 120, for T2 is 180
    assert res[0].path == ["A", "B", "D"]
    assert res[0].fastest_duration_minutes == 120
    assert res[1].path == ["A", "C", "D"]
    assert res[1].fastest_duration_minutes == 180

def test_missing_timing_in_one_occurrence(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1")
    t2 = Train(number="T2")
    db_session.add_all([t1, t2])
    db_session.flush()

    # T1 has valid timing
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", source_day=1),
    ])
    
    # T2 is missing timing
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id, departure_time=None, source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s2.id, arrival_time="14:30", source_day=1),
    ])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res) == 1
    assert res[0].occurrence_count == 2
    assert res[0].fastest_duration_minutes == 60 # Falls back to the valid one

def test_missing_timing_in_all_occurrences(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1")
    db_session.add_all([t1])
    db_session.flush()

    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=None),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", source_day=1),
    ])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res) == 1
    assert res[0].occurrence_count == 1
    assert res[0].fastest_duration_minutes is None

def test_reverse_direction_is_separate(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()
    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1")
    db_session.add(t1)
    db_session.flush()

    # B to A
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s2.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s1.id, arrival_time="11:00", source_day=1),
    ])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res) == 0

    res = find_network_corridors(db_session, 1, s2.id, s1.id)
    assert len(res) == 1
    assert res[0].path == ["B", "A"]

def test_origin_after_destination(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()
    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1")
    db_session.add(t1)
    db_session.flush()

    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s2.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s1.id, arrival_time="11:00", source_day=1),
    ])
    db_session.flush()

    # Should not match A->B because A appears after B for this train
    res = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res) == 0

def test_same_station_validation(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    db_session.add_all([s1])
    db_session.flush()
    setup_basic_graph(db_session, source.id)

    with pytest.raises(ValueError, match="Origin and destination must not be the same"):
        find_network_corridors(db_session, 1, s1.id, s1.id)

def test_active_graph_build_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    # Create snapshot without graph build
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_network_corridors(db_session, 1, s1.id, s2.id)

    # Create FAILED graph build
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="FAILED")
    db_session.add(gb)
    db_session.flush()

    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_network_corridors(db_session, 1, s1.id, s2.id)

def test_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    setup_basic_graph(db_session, source.id, snapshot_id=1)
    setup_basic_graph(db_session, source.id, snapshot_id=2)

    t1 = Train(number="T1")
    db_session.add(t1)
    db_session.flush()

    # Train goes A->B in snapshot 2
    db_session.add_all([
        TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00", source_day=1),
    ])
    db_session.flush()

    res1 = find_network_corridors(db_session, 1, s1.id, s2.id)
    assert len(res1) == 0

    res2 = find_network_corridors(db_session, 2, s1.id, s2.id)
    assert len(res2) == 1
    assert res2[0].path == ["A", "B"]

def test_deterministic_ordering(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()
    setup_basic_graph(db_session, source.id)

    t1 = Train(number="T1")
    t2 = Train(number="T2")
    t3 = Train(number="T3")
    db_session.add_all([t1, t2, t3])
    db_session.flush()

    # All have count=1.
    # T1: duration=60, path A->B->D
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="10:30", departure_time="10:30", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s4.id, arrival_time="11:00", source_day=1),
    ])

    # T2: duration=60, path A->C->D
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s3.id, arrival_time="10:30", departure_time="10:30", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=3, station_id=s4.id, arrival_time="11:00", source_day=1),
    ])

    # T3: duration=120, path A->D
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=1, station_id=s1.id, departure_time="10:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=2, station_id=s4.id, arrival_time="12:00", source_day=1),
    ])
    db_session.flush()

    res = find_network_corridors(db_session, 1, s1.id, s4.id)
    assert len(res) == 3
    
    # 1. occurrence_count DESC (all 1)
    # 2. fastest_duration_minutes ASC (60, 60, 120)
    # 3. array_length ASC (T1=3, T2=3, T3=2) 
    # WAIT! T3 has length 2, but its duration is 120. Duration takes precedence over array length!
    # So T1 and T2 are first.
    # T1 path A->B->D vs T2 path A->C->D. Array length is same.
    # String comparison: A,B,D vs A,C,D. B < C, so T1 before T2.
    # Therefore order: T1, T2, T3
    
    assert res[0].path == ["A", "B", "D"]
    assert res[1].path == ["A", "C", "D"]
    assert res[2].path == ["A", "D"]

