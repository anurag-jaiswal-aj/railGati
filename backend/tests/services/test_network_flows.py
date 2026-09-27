import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_network_flows


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    return source


def setup_stations(db_session: Session) -> tuple[Station, Station, Station]:
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Station B"),
            StationObservation(snapshot_id=1, station_id=s3.id, name="Station C"),
        ]
    )
    db_session.flush()
    return s1, s2, s3


@pytest.fixture
def flow_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    # Train 1: A -> B -> C (Flow A -> C)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id),
        ]
    )

    # Train 2: C -> B (Flow C -> B)
    t2 = Train(number="102")
    db_session.add(t2)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"))
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s3.id),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s2.id),
        ]
    )

    # Train 3: Loop A -> B -> A (Flow A -> A)
    t3 = Train(number="103")
    db_session.add(t3)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t3.id, name="T3"))
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=3, station_id=s1.id),
        ]
    )

    # Train 4: A -> B -> C (Flow A -> C) - duplicate occurrence
    t4 = Train(number="104")
    db_session.add(t4)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t4.id, name="T4"))
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=3, station_id=s3.id),
        ]
    )

    db_session.flush()


def test_calculate_network_flows_basic(db_session: Session, flow_test_data: None) -> None:
    flows = calculate_network_flows(db_session, 1)

    # Flows:
    # A -> C: 2 occurrences
    # A -> A: 1 occurrence
    # C -> B: 1 occurrence
    # Order: volume DESC, orig ASC, dest ASC
    # A->C (2)
    # A->A (1)
    # C->B (1)

    assert len(flows) == 3

    assert flows[0].origin_station_code == "A"
    assert flows[0].destination_station_code == "C"
    assert flows[0].flow_volume == 2

    assert flows[1].origin_station_code == "A"
    assert flows[1].destination_station_code == "A"
    assert flows[1].flow_volume == 1

    assert flows[2].origin_station_code == "C"
    assert flows[2].destination_station_code == "B"
    assert flows[2].flow_volume == 1


def test_calculate_network_flows_limit(db_session: Session, flow_test_data: None) -> None:
    flows = calculate_network_flows(db_session, 1, limit=1)
    assert len(flows) == 1
    assert flows[0].origin_station_code == "A"
    assert flows[0].destination_station_code == "C"


def test_calculate_network_flows_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()

    # Train in snapshot 2 (Flow A -> B)
    db_session.add(TrainObservation(snapshot_id=2, train_id=t1.id, name="T1"))
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=2, station_id=s2.id),
        ]
    )
    db_session.flush()

    # Query snapshot 1 (should be empty)
    flows = calculate_network_flows(db_session, 1)
    assert len(flows) == 0

    # Query snapshot 2 (should find A -> B)
    flows2 = calculate_network_flows(db_session, 2)
    assert len(flows2) == 1
    assert flows2[0].origin_station_code == "A"
    assert flows2[0].destination_station_code == "B"


def test_calculate_network_flows_incomplete_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()

    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.flush()

    # Train 101 has NO stops.
    flows = calculate_network_flows(db_session, 1)
    assert len(flows) == 0
