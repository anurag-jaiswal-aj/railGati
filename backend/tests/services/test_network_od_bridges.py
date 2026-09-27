import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_od_bridges


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
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s_orig.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s_dest.id,
                arrival_time="11:00:00",
                source_day=1,
            ),
        ]
    )
    db_session.commit()


def test_service_network_od_bridges_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_station_od_bridges(db_session, 1, "ORG")
    assert result["station_code"] == "ORG"
    assert result["unique_origins_count"] == 1
    assert result["unique_destinations_count"] == 1
    assert result["unique_od_pairs_count"] == 1

    pairs = result["top_od_pairs"]
    assert len(pairs) == 1
    assert pairs[0]["origin_station_code"] == "ORG"
    assert pairs[0]["destination_station_code"] == "DST"


def test_service_network_od_bridges_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_od_bridges(db_session, 1, "XXX")
