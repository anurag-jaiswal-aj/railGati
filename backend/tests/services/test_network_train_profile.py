import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_profile


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_orig = Station(code="ORG")
    s_dest = Station(code="DST")
    db_session.add_all([s_orig, s_dest])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_orig.id, name="Origin"),
            StationObservation(snapshot_id=1, station_id=s_dest.id, name="Dest"),
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
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_dest.id, arrival_time="11:00:00", source_day=1),
        ]
    )
    db_session.commit()


def test_service_network_train_profile_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_train_profile(db_session, 1, "12345")
    assert result["train_number"] == "12345"
    assert result["origin_station_code"] == "ORG"
    assert result["destination_station_code"] == "DST"
    assert result["total_stops"] == 2
    assert result["total_duration_minutes"] == 60.0
    assert result["total_dwell_minutes"] == 0.0
    assert result["dwell_percentage"] == 0.0

def test_service_network_train_profile_invalid_train(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_train_profile(db_session, 1, "99999")
