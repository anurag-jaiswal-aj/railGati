import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_network_od_travel_time


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_ndls = Station(code="NDLS")
    s_cnb = Station(code="CNB")
    s_mtd = Station(code="MTD")
    s_dna = Station(code="DNA")
    s_xx = Station(code="XX")
    db_session.add_all([s_ndls, s_cnb, s_mtd, s_dna, s_xx])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_ndls.id, name="New Delhi"),
            StationObservation(snapshot_id=1, station_id=s_cnb.id, name="Kanpur"),
            StationObservation(snapshot_id=1, station_id=s_mtd.id, name="Merta"),
            StationObservation(snapshot_id=1, station_id=s_dna.id, name="Degana"),
            StationObservation(snapshot_id=1, station_id=s_xx.id, name="Unknown"),
        ]
    )

    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", type="EXP"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )

    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                arrival_time=None,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s_xx.id,
                arrival_time="12:00:00",
                departure_time="12:10:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=3,
                station_id=s_cnb.id,
                arrival_time="14:34:00",
                departure_time=None,
                source_day=1,
            ),
        ]
    )

    db_session.commit()


def test_service_network_travel_time_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_network_od_travel_time(db_session, 1, "NDLS", "CNB")
    assert result[0] == "NDLS"
    assert result[1] == "New Delhi"
    assert result[2] == "CNB"
    assert result[3] == "Kanpur"
    assert result[4] == 1  # qual
    assert result[5] == 1  # dist
    assert result[6] == 274  # min
    assert result[7] == 274  # max
    assert result[8] == 274.0  # avg


def test_service_network_travel_time_invalid_station(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_network_od_travel_time(db_session, 1, "XXX", "CNB")

    with pytest.raises(ValueError, match="must be different"):
        calculate_network_od_travel_time(db_session, 1, "NDLS", "NDLS")
