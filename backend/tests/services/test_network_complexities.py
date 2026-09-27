from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_network_complexities


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


def test_calculate_network_complexities_basic(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    # Train 1: 3 stops. Visits A, B, C
    t1 = Train(number="101")
    # Train 2: 2 stops. Visits A, B
    t2 = Train(number="102")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )
    db_session.flush()

    # T1 Stops
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id),
        ]
    )
    # T2 Stops
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s2.id),
        ]
    )
    db_session.flush()

    # Station A: T1 (3 stops), T2 (2 stops) -> AVG = 2.5, count = 2
    # Station B: T1 (3 stops), T2 (2 stops) -> AVG = 2.5, count = 2
    # Station C: T1 (3 stops) -> AVG = 3.0, count = 1
    complexities = calculate_network_complexities(db_session, 1, 1, min_service_count=1)

    assert len(complexities) == 3

    # Ordered by avg DESC, then service_count DESC
    assert complexities[0].station_code == "C"
    assert complexities[0].avg_route_stops == 3.0
    assert complexities[0].service_count == 1

    assert complexities[1].station_code == "A"
    assert complexities[1].avg_route_stops == 2.5
    assert complexities[1].service_count == 2

    assert complexities[2].station_code == "B"
    assert complexities[2].avg_route_stops == 2.5
    assert complexities[2].service_count == 2


def test_calculate_network_complexities_min_service_count(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    t1 = Train(number="101")
    t2 = Train(number="102")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )

    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s2.id),
        ]
    )
    db_session.flush()

    # Require minimum of 2 transits. C has only 1, so it should be excluded.
    complexities = calculate_network_complexities(db_session, 1, 1, min_service_count=2)
    assert len(complexities) == 2
    codes = {c.station_code for c in complexities}
    assert "C" not in codes
    assert "A" in codes
    assert "B" in codes


def test_calculate_network_complexities_limit(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

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
    db_session.flush()

    complexities = calculate_network_complexities(db_session, 1, 1, limit=2, min_service_count=1)
    assert len(complexities) == 2


def test_calculate_network_complexities_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add_all(
        [
            DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"),
            DatasetSnapshot(id=2, source_id=source.id, status="SUPERSEDED"),
        ]
    )
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=2, train_id=t1.id, name="T1"),
        ]
    )

    # Snapshot 2 data - should not affect Snapshot 1 query
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=2, train_id=t1.id, stop_sequence=3, station_id=s3.id),
        ]
    )
    db_session.flush()

    # Query snapshot 1 (should be empty)
    complexities = calculate_network_complexities(db_session, 1, 1, min_service_count=1)
    assert len(complexities) == 0
