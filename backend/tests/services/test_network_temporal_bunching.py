import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_edge_temporal_bunching


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

    t1 = Train(number="0001")
    t2 = Train(number="0002")
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
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_dest.id, arrival_time="11:00:00", source_day=1), 
            
            # Exactly 60 minutes later! (should NOT be in the window of 10:00 since it is half-open)
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s_orig.id, departure_time="11:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s_dest.id, arrival_time="12:00:00", source_day=1),
        ]
    )
    db_session.commit()


def test_service_network_bunching_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_edge_temporal_bunching(db_session, 1, "ORG", "DST")
    assert result is not None
    assert result["origin_station_code"] == "ORG"
    assert result["destination_station_code"] == "DST"
    assert result["total_edge_volume"] == 2
    # Because 11:00 is >= 10:00 + 60, it does not fall into the 10:00 window.
    # Therefore max count is 1.
    assert result["peak_60min_trains"] == 1

def test_service_network_bunching_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="(?i)not found"):
        calculate_edge_temporal_bunching(db_session, 1, "XXX", "DST")

def test_service_network_bunching_no_edge(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="(?i)no qualifying adjacent timetable edge found"):
        calculate_edge_temporal_bunching(db_session, 1, "DST", "ORG")

def test_service_network_bunching_same_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="(?i)cannot be the same station"):
        calculate_edge_temporal_bunching(db_session, 1, "ORG", "ORG")
