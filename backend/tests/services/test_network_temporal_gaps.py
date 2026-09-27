import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_temporal_gaps


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="STA")
    s2 = Station(code="STB")
    db_session.add_all([s1, s2])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station 1"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Station 2"),
        ]
    )

    t1 = Train(number="12345")
    db_session.add_all([t1])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
        ]
    )

    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s1.id,
                departure_time="10:00:00",
                source_day=1,
            ),  # duplicate
        ]
    )
    db_session.commit()


def test_service_network_temporal_gaps_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_station_temporal_gaps(db_session, 1, "STA")
    assert result["station_code"] == "STA"
    assert result["total_departures"] == 2
    # Duplicate departs give a gap of 0, plus wrap-around gap of 1440
    # Average: (1440 + 0) / 2 = 720.0
    assert result["max_departure_gap_minutes"] == 1440.0
    assert result["average_departure_gap_minutes"] == 720.0


def test_service_network_temporal_gaps_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_temporal_gaps(db_session, 1, "XXX")


def test_service_network_temporal_gaps_no_departures(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="(?i)no qualifying departures"):
        calculate_station_temporal_gaps(db_session, 1, "STB")
