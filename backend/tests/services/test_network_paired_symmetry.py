import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_paired_service_symmetry


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_service", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    t1 = Train(number="12301")
    t2 = Train(number="12302")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", return_train_number="12302"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2", return_train_number="12301"),
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
                station_id=s2.id,
                arrival_time="03:00:00",
                source_day=2,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=1,
                station_id=s2.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s1.id,
                arrival_time="02:55:00",
                source_day=2,
            ),
        ]
    )
    db_session.commit()


def test_service_network_paired_symmetry_success(db_session: Session) -> None:
    setup_data(db_session)
    result = calculate_paired_service_symmetry(db_session, 1, "12301")
    assert result is not None
    assert result["train_number"] == "12301"
    assert result["return_train_number"] == "12302"
    assert result["forward_train_duration_minutes"] == 1020.0
    assert result["return_train_duration_minutes"] == 1015.0
    assert result["duration_asymmetry_minutes"] == 5.0


def test_service_network_paired_symmetry_invalid_train(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="(?i)not found"):
        calculate_paired_service_symmetry(db_session, 1, "XXX")


def test_service_network_paired_symmetry_missing_snapshot(db_session: Session) -> None:
    setup_data(db_session)
    with pytest.raises(ValueError, match="(?i)snapshot not found"):
        calculate_paired_service_symmetry(db_session, 999, "12301")
