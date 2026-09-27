import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_outbound_transit


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_ndls = Station(code="NDLS")
    s_csb = Station(code="CSB")
    db_session.add_all([s_ndls, s_csb])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_ndls.id, name="New Delhi"),
            StationObservation(snapshot_id=1, station_id=s_csb.id, name="Shivaji Bridge"),
        ]
    )

    t1 = Train(number="0001")
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
                station_id=s_ndls.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s_csb.id,
                arrival_time="10:05:00",
                source_day=1,
            ),
        ]
    )
    db_session.commit()


def test_service_network_outbound_transit_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_station_outbound_transit(db_session, 1, "NDLS")
    assert result[0] == "NDLS"
    assert result[1] == "New Delhi"

    edges = result[2]
    assert len(edges) == 1
    assert edges[0]["next_station_code"] == "CSB"
    assert edges[0]["train_volume"] == 1
    assert edges[0]["min_duration_minutes"] == 5.0


def test_service_network_outbound_transit_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_outbound_transit(db_session, 1, "XXX")
