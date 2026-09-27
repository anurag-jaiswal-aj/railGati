import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_reversals


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_vskp = Station(code="VSKP")
    s_mipm = Station(code="MIPM")
    db_session.add_all([s_vskp, s_mipm])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_vskp.id, name="Visakhapatnam"),
            StationObservation(snapshot_id=1, station_id=s_mipm.id, name="Marripalem"),
        ]
    )

    t1 = Train(number="11019")
    db_session.add_all([t1])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
        ]
    )

    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_mipm.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_vskp.id, arrival_time="20:55:00", departure_time="21:15:00"),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s_mipm.id),
        ]
    )
    db_session.commit()


def test_service_network_reversals_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_station_reversals(db_session, 1, "VSKP")
    assert result[0] == "VSKP"
    assert result[1] == "Visakhapatnam"
    assert result[2] == 1 # count
    
    trains = result[3]
    assert len(trains) == 1
    assert trains[0]["train_number"] == "11019"
    assert trains[0]["adjoining_station_code"] == "MIPM"
    assert trains[0]["arrival_time"] == "20:55:00"
    assert trains[0]["departure_time"] == "21:15:00"

def test_service_network_reversals_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_reversals(db_session, 1, "XXX")
