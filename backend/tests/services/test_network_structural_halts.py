import typing
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station
from railgati.models.train import Train
from railgati.services.network import calculate_train_structural_halts


@pytest.fixture
def setup_service_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    train = Train(
        id=1,
        number="12004",
    )
    db_session.add(train)
    db_session.flush()

    train_linear = Train(
        id=2,
        number="12301",
    )
    db_session.add(train_linear)
    db_session.flush()

    stations = []
    for code in ["NDLS", "CNB", "ETW", "GZB"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    # Observations for train 1
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations 
        (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 1, :s1, 1, NULL, '10:00:00'),
        (2, 1, :s2, 2, '12:00:00', '12:05:00'),  -- 5 mins
        (2, 1, :s3, 3, '13:00:00', '13:02:00'),  -- 2 mins
        (2, 1, :s4, 4, '14:00:00', NULL)
    """),
        {"s1": s_map["NDLS"], "s2": s_map["CNB"], "s3": s_map["ETW"], "s4": s_map["GZB"]},
    )

    # Observations for train 2 (Only 2 stops)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations 
        (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 2, :s1, 1, NULL, '10:00:00'),
        (2, 2, :s4, 2, '14:00:00', NULL)
    """),
        {"s1": s_map["NDLS"], "s4": s_map["GZB"]},
    )

    db_session.commit()
    return snapshot, train, s_map


def test_calculate_train_structural_halts(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_structural_halts(db_session, 2, "12004")
    assert result["train_number"] == "12004"
    assert result["timetable_snapshot_id"] == 2
    assert len(result["halts"]) == 2
    assert result["halts"][0]["station_code"] == "CNB"
    assert result["halts"][0]["dwell_minutes"] == 5.0
    assert result["halts"][1]["station_code"] == "ETW"
    assert result["halts"][1]["dwell_minutes"] == 2.0


def test_calculate_train_structural_halts_empty(db_session: Session, setup_service_data: typing.Any) -> None:
    # Train 12301 has only 2 stops, so no intermediate halts
    result = calculate_train_structural_halts(db_session, 2, "12301")
    assert result["train_number"] == "12301"
    assert result["timetable_snapshot_id"] == 2
    assert len(result["halts"]) == 0


def test_calculate_train_structural_halts_unknown_train(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_structural_halts(db_session, 2, "99999")
