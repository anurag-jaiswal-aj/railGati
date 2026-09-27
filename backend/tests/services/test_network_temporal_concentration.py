from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_network_temporal_concentration


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


def test_calculate_network_temporal_concentration_basic(db_session: Session) -> None:
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
            # Station A: 22:00, 22:05 (both fall in hour 22). Total = 2, Peak = 2, % = 100
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="22:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="22:05:00",
            ),
            # Station B: 12:00, 13:00, 13:30. Total = 3, Peak = 2 (hour 13), % = 66.7
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="11:50:00",
                departure_time="12:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="13:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=3,
                station_id=s2.id,
                arrival_time="13:30:00",
            ),
            # Station C: Null times. Should be excluded.
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=4, station_id=s3.id),
        ]
    )
    db_session.flush()

    concentrations = calculate_network_temporal_concentration(db_session, 1, 1, min_service_count=1)

    assert len(concentrations) == 2

    # Station A
    assert concentrations[0].station_code == "A"
    assert concentrations[0].peak_hour_val == 22
    assert concentrations[0].peak_hour_volume == 2
    assert concentrations[0].total_volume == 2
    assert concentrations[0].concentration_pct == 100.0

    # Station B
    assert concentrations[1].station_code == "B"
    assert concentrations[1].peak_hour_val == 13
    assert concentrations[1].peak_hour_volume == 2
    assert concentrations[1].total_volume == 3
    assert concentrations[1].concentration_pct == 66.7


def test_temporal_concentration_coalesce_and_ties(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, _, _ = setup_stations(db_session)

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
            # Arrival in 15, Departure in 16. Should use departure (16).
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                arrival_time="15:55:00",
                departure_time="16:05:00",
            ),
            # Only Arrival in 16. Uses arrival (16).
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=1,
                station_id=s1.id,
                arrival_time="16:30:00",
            ),
            # Arrival in 09, Departure in 09.
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s1.id,
                departure_time="09:10:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s1.id,
                departure_time="09:15:00",
            ),
        ]
    )
    db_session.flush()

    # Station A has 2 events in hour 16, 2 events in hour 09. Tie!
    # Tie breaking uses MIN(event_hour) -> 9.
    concentrations = calculate_network_temporal_concentration(db_session, 1, 1, min_service_count=1)

    assert len(concentrations) == 1
    assert concentrations[0].station_code == "A"
    assert concentrations[0].peak_hour_val == 9
    assert concentrations[0].peak_hour_volume == 2
    assert concentrations[0].total_volume == 4
    assert concentrations[0].concentration_pct == 50.0


def test_temporal_concentration_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add_all(
        [
            DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"),
            DatasetSnapshot(id=2, source_id=source.id, status="SUPERSEDED"),
        ]
    )
    db_session.flush()

    s1, _, _ = setup_stations(db_session)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=2, train_id=t1.id, name="T1"),
        ]
    )

    # Snapshot 2 data
    db_session.add(
        TrainStopObservation(
            snapshot_id=2,
            train_id=t1.id,
            stop_sequence=1,
            station_id=s1.id,
            departure_time="10:00:00",
        )
    )
    db_session.flush()

    # Query snapshot 1
    concentrations = calculate_network_temporal_concentration(db_session, 1, 1, min_service_count=1)
    assert len(concentrations) == 0
