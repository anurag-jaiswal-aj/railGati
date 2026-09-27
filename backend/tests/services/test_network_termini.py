import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_network_termini


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
def terminus_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    # Train 1: A -> B -> C
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))

    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id),
    ])

    # Train 2: C -> B (Return train technically, but we don't merge them)
    t2 = Train(number="102")
    db_session.add(t2)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"))

    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s3.id),
        TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s2.id),
    ])

    # Train 3: Loop A -> B -> A
    t3 = Train(number="103")
    db_session.add(t3)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t3.id, name="T3"))

    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=1, station_id=s1.id),
        TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=2, station_id=s2.id),
        TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=3, station_id=s1.id),
    ])

    db_session.flush()


def test_calculate_network_termini_basic(db_session: Session, terminus_test_data: None) -> None:
    termini = calculate_network_termini(db_session, 1)

    # We have A, B, C.
    # Train 1: origin A, terminus C
    # Train 2: origin C, terminus B
    # Train 3: origin A, terminus A
    # Total for A: orig = 2, term = 1 => 3
    # Total for C: orig = 1, term = 1 => 2
    # Total for B: orig = 0, term = 1 => 1

    assert len(termini) == 3

    assert termini[0].station_code == "A"
    assert termini[0].originating_count == 2
    assert termini[0].terminating_count == 1
    assert termini[0].total_terminus_volume == 3

    assert termini[1].station_code == "C"
    assert termini[1].originating_count == 1
    assert termini[1].terminating_count == 1
    assert termini[1].total_terminus_volume == 2

    assert termini[2].station_code == "B"
    assert termini[2].originating_count == 0
    assert termini[2].terminating_count == 1
    assert termini[2].total_terminus_volume == 1


def test_calculate_network_termini_limit(db_session: Session, terminus_test_data: None) -> None:
    termini = calculate_network_termini(db_session, 1, limit=1)
    assert len(termini) == 1
    assert termini[0].station_code == "A"


def test_calculate_network_termini_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()

    # Train in snapshot 2
    db_session.add(TrainObservation(snapshot_id=2, train_id=t1.id, name="T1"))
    db_session.add_all([
        TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=1, station_id=s1.id),
        TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=2, station_id=s2.id),
    ])
    db_session.flush()

    # Query snapshot 1 (should be empty)
    termini = calculate_network_termini(db_session, 1)
    assert len(termini) == 0

    # Query snapshot 2 (should find A and B)
    termini2 = calculate_network_termini(db_session, 2)
    assert len(termini2) == 2


def test_calculate_network_termini_incomplete_data(db_session: Session) -> None:
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
    termini = calculate_network_termini(db_session, 1)
    assert len(termini) == 0
