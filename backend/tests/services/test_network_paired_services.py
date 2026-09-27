import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_paired_services


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_ndls = Station(code="NDLS")
    s_other = Station(code="OTHER")
    db_session.add_all([s_ndls, s_other])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_ndls.id, name="New Delhi"),
            StationObservation(snapshot_id=1, station_id=s_other.id, name="Other"),
        ]
    )

    t1 = Train(number="12486")
    t2 = Train(number="12485")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", return_train_number="12485"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )

    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_other.id, departure_time="20:00:00"),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_ndls.id, arrival_time="23:20:00"),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s_ndls.id, departure_time="01:40:00"),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s_other.id, arrival_time="05:00:00"),
        ]
    )
    db_session.commit()


def test_service_network_paired_services_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_station_paired_services(db_session, 1, "NDLS")
    assert result[0] == "NDLS"
    assert result[1] == "New Delhi"
    assert result[2] == 1 # count
    assert result[3] == 140.0 # avg
    
    pairs = result[4]
    assert len(pairs) == 1
    assert pairs[0]["arriving_train_number"] == "12486"
    assert pairs[0]["departing_train_number"] == "12485"
    assert pairs[0]["arrival_time"] == "23:20:00"
    assert pairs[0]["departure_time"] == "01:40:00"
    assert pairs[0]["clock_gap_minutes"] == 140

def test_service_network_paired_services_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_paired_services(db_session, 1, "XXX")
