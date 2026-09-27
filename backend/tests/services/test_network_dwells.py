import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_network_dwells


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    return source


def setup_stations(db_session: Session) -> tuple[Station, Station, Station, Station]:
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Station B"),
            StationObservation(snapshot_id=1, station_id=s3.id, name="Station C"),
            StationObservation(snapshot_id=1, station_id=s4.id, name="Station D"),
        ]
    )
    db_session.flush()
    return s1, s2, s3, s4


@pytest.fixture
def dwell_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3, s4 = setup_stations(db_session)

    # Train 1: A -> B -> C
    # B is transit: arrival 10:00, departure 10:15 => 15 mins dwell
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="09:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="10:00:00",
                departure_time="10:15:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=3,
                station_id=s3.id,
                arrival_time="11:00:00",
            ),
        ]
    )

    # Train 2: A -> B -> D
    # B is transit: arrival 23:50, departure 00:10 => midnight crossing => 20 mins dwell
    t2 = Train(number="102")
    db_session.add(t2)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"))
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="22:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="23:50:00",
                departure_time="00:10:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=3,
                station_id=s4.id,
                arrival_time="01:00:00",
            ),
        ]
    )

    # Train 3: C -> B -> D
    # B is transit: arrival 14:00, departure 14:00 => 0 mins dwell, excluded by condition (arrival != departure)
    t3 = Train(number="103")
    db_session.add(t3)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t3.id, name="T3"))
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=1,
                station_id=s3.id,
                departure_time="13:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="14:00:00",
                departure_time="14:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=3,
                station_id=s4.id,
                arrival_time="15:00:00",
            ),
        ]
    )

    # Train 4: A -> D -> C
    # D is transit: arrival 08:00, departure 08:30 => 30 mins dwell
    t4 = Train(number="104")
    db_session.add(t4)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t4.id, name="T4"))
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="07:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=2,
                station_id=s4.id,
                arrival_time="08:00:00",
                departure_time="08:30:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=3,
                station_id=s3.id,
                arrival_time="09:00:00",
            ),
        ]
    )

    db_session.flush()


def test_calculate_network_dwells_basic(db_session: Session, dwell_test_data: None) -> None:
    # min_transit_count=1 to include all test data
    dwells = calculate_network_dwells(db_session, 1, min_transit_count=1)

    # Expected:
    # D: 1 transit, 30 mins
    # B: 2 valid transits (15 mins, 20 mins) => avg = 17.5 mins. (The 0-min transit is excluded).
    # A, C are never valid transits (only origin/terminus).

    assert len(dwells) == 2

    # Order: avg_dwell_minutes DESC
    assert dwells[0].station_code == "D"
    assert dwells[0].avg_dwell_minutes == 30.0
    assert dwells[0].transit_count == 1

    assert dwells[1].station_code == "B"
    assert dwells[1].avg_dwell_minutes == 17.5
    assert dwells[1].transit_count == 2


def test_calculate_network_dwells_min_transit_count(
    db_session: Session, dwell_test_data: None
) -> None:
    # Requires 2 transits minimum
    dwells = calculate_network_dwells(db_session, 1, min_transit_count=2)

    assert len(dwells) == 1
    assert dwells[0].station_code == "B"
    assert dwells[0].transit_count == 2


def test_calculate_network_dwells_limit(db_session: Session, dwell_test_data: None) -> None:
    dwells = calculate_network_dwells(db_session, 1, limit=1, min_transit_count=1)
    assert len(dwells) == 1
    assert dwells[0].station_code == "D"


def test_calculate_network_dwells_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3, _ = setup_stations(db_session)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()

    # Train in snapshot 2
    db_session.add(TrainObservation(snapshot_id=2, train_id=t1.id, name="T1"))
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=2,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="10:00:00",
            ),
            TrainStopObservation(
                snapshot_id=2,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="11:00:00",
                departure_time="12:00:00",
            ),
            TrainStopObservation(
                snapshot_id=2,
                train_id=t1.id,
                stop_sequence=3,
                station_id=s3.id,
                arrival_time="13:00:00",
            ),
        ]
    )
    db_session.flush()

    # Query snapshot 1 (should be empty)
    dwells = calculate_network_dwells(db_session, 1, min_transit_count=1)
    assert len(dwells) == 0

    # Query snapshot 2
    dwells2 = calculate_network_dwells(db_session, 2, min_transit_count=1)
    assert len(dwells2) == 1
    assert dwells2[0].station_code == "B"
    assert dwells2[0].avg_dwell_minutes == 60.0
