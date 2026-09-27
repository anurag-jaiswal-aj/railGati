import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation
from railgati.services.network import calculate_train_relative_station_dwell


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

    # Create trains
    # 15905 Target
    # 15906 Peer
    # 04853 Repeated Target
    # 99999 Empty Target (ratio <= 1.0)
    # 00000 ZEROAVG Target
    # 11111 MISSING Target
    # 22222 MIDNIGHT Target
    t1 = Train(id=1, number="15905")
    t2 = Train(id=2, number="15906")
    t_empty = Train(id=3, number="99999")
    t_repeated = Train(id=4, number="04853")
    t_zero = Train(id=5, number="ZEROAVG")
    t_missing = Train(id=6, number="MISSING")
    t_midnight = Train(id=7, number="MIDNIGHT")

    db_session.add_all([t1, t2, t_empty, t_repeated, t_zero, t_missing, t_midnight])
    db_session.flush()

    stations = []
    for code in ["A", "B", "C", "D"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    # Helper for adding stops
    def add_stop(train_id, st_code, seq, arr, dep):
        db_session.execute(
            text(
                "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, :t, :s, :seq, :a, :d)"
            ),
            {"t": train_id, "s": s_map[st_code], "seq": seq, "a": arr, "d": dep},
        )

    # 15905 Target: A (origin), B (intermediate), C (dest)
    # B target dwell = 60 mins (11:00 to 12:00)
    add_stop(1, "A", 1, None, "10:00:00")
    add_stop(1, "B", 2, "11:00:00", "12:00:00")
    add_stop(1, "C", 3, "13:00:00", None)

    # 15906 Peer: A (origin), B (intermediate), C (dest)
    # B peer dwell = 20 mins (11:10 to 11:30)
    # B network avg = (60+20)/2 = 40. Count = 2.
    add_stop(2, "A", 1, None, "10:00:00")
    add_stop(2, "B", 2, "11:10:00", "11:30:00")
    add_stop(2, "C", 3, "13:00:00", None)

    # 04853 Repeated Target: A (origin), B (int 1), C (int), B (int 2), D (dest)
    # B seq 2 dwell = 60 mins (11:00 to 12:00)
    # B seq 4 dwell = 20 mins (14:00 to 14:20)
    # Peer 2 B dwell = 20 mins (added above)
    # Peer 2 also visits B seq 4? No, just use Peer 15906 B seq 2.
    # For 04853: B network avg = (60+20+20) / 3 = 33.3 mins. Count = 3.
    # B seq 2 ratio = 60 / 33.3 = 1.8 (>1.0)
    # B seq 4 ratio = 20 / 33.3 = 0.6 (<1.0)
    add_stop(4, "A", 1, None, "10:00:00")
    add_stop(4, "B", 2, "11:00:00", "12:00:00")
    add_stop(4, "C", 3, "13:00:00", "13:10:00")
    add_stop(4, "B", 4, "14:00:00", "14:20:00")
    add_stop(4, "D", 5, "15:00:00", None)

    # 99999 Empty Target: A (origin), B (int), C (dest)
    # B target dwell = 20 mins (11:00 to 11:20)
    # Peer 15906 B dwell = 20 mins
    # Peer 15905 B dwell = 60 mins
    # Avg for B is (60+20+20)/3 = 33.3. Ratio = 20 / 33.3 < 1.
    add_stop(3, "A", 1, None, "10:00:00")
    add_stop(3, "B", 2, "11:00:00", "11:20:00")
    add_stop(3, "C", 3, "12:00:00", None)

    # ZEROAVG Target: A (origin), D (int), C (dest)
    # D target dwell = 0 mins
    # Peer also D dwell = 0 mins
    add_stop(5, "A", 1, None, "10:00:00")
    add_stop(5, "D", 2, "11:00:00", "11:00:00")
    add_stop(5, "C", 3, "12:00:00", None)

    add_stop(2, "D", 5, "11:30:00", "11:30:00")  # Peer D 0 min dwell

    # MISSING Target: A (origin), C (int), B (dest)
    # Target C missing departure
    add_stop(6, "A", 1, None, "10:00:00")
    add_stop(6, "C", 2, "11:00:00", None)
    add_stop(6, "B", 3, "12:00:00", None)

    # Peer C missing arrival -> excluded from baseline
    add_stop(2, "C", 6, None, "11:00:00")

    # MIDNIGHT Target: A (origin), C (int), D (dest)
    # Target C 23:55 to 00:10 (15 mins)
    # Peer C 23:00 to 23:05 (5 mins)
    add_stop(7, "A", 1, None, "23:00:00")
    add_stop(7, "C", 2, "23:55:00", "00:10:00")
    add_stop(7, "D", 3, "01:00:00", None)

    add_stop(2, "C", 7, "23:00:00", "23:05:00")

    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))
    db_session.commit()
    return snapshot, t1, s_map


def test_calculate_train_relative_station_dwell_basic(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    # 15905 has B target = 60. Peers B = 20 (from 15906), 60 (from 04853), 20 (from 04853), 20 (from 99999).
    # Wait, ALL trains contribute to the network baseline for B.
    # Total B network dwells:
    # 15905: 60
    # 15906: 20
    # 04853 seq 2: 60
    # 04853 seq 4: 20
    # 99999: 20
    # Sum = 180. Count = 5. Avg = 36.0.
    # 15905 Ratio = 60 / 36 = 1.666...
    result = calculate_train_relative_station_dwell(db_session, 2, "15905")
    assert result["train_number"] == "15905"
    assert result["timetable_snapshot_id"] == 2

    assert len(result["relative_dwells"]) == 1
    dwell = result["relative_dwells"][0]
    assert dwell["station_code"] == "B"
    assert dwell["target_dwell_minutes"] == 60.0
    assert dwell["network_average_minutes"] == 36.0
    assert dwell["network_occurrence_count"] == 5
    assert dwell["slowness_ratio"] == 60.0 / 36.0


def test_calculate_repeated_station_dwells(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    result = calculate_train_relative_station_dwell(db_session, 2, "04853")

    # B avg = 36.0
    # 04853 seq 2 = 60 -> Ratio 60/36 = 1.66 (>1)
    # 04853 seq 4 = 20 -> Ratio 20/36 = 0.55 (<1)
    # C target = 10 (from 13:00 to 13:10)
    # C peer = 5 (from 23:00 to 23:05), C midnight = 15
    # C avg = (10+5+15)/3 = 10.
    # C ratio = 10/10 = 1.0 (excluded)

    assert len(result["relative_dwells"]) == 1
    dwell = result["relative_dwells"][0]
    assert dwell["target_stop_sequence"] == 2
    assert dwell["station_code"] == "B"
    assert (
        dwell["network_occurrence_count"] == 5
    )  # Ensures we don't multiply by 2 because 04853 visits B twice
    assert dwell["slowness_ratio"] == 60.0 / 36.0


def test_calculate_unknown_train(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_relative_station_dwell(db_session, 2, "00000")


def test_calculate_empty_dwells(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_station_dwell(db_session, 2, "99999")
    assert result["relative_dwells"] == []


def test_calculate_zero_average(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_station_dwell(db_session, 2, "ZEROAVG")
    assert result["relative_dwells"] == []


def test_calculate_missing_timings(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_station_dwell(db_session, 2, "MISSING")
    assert result["relative_dwells"] == []


def test_calculate_cross_midnight(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_station_dwell(db_session, 2, "MIDNIGHT")
    # C avg = 10. Target = 15.
    # Ratio = 1.5
    assert len(result["relative_dwells"]) == 1
    dwell = result["relative_dwells"][0]
    assert dwell["station_code"] == "C"
    assert dwell["target_dwell_minutes"] == 15.0
    assert dwell["network_average_minutes"] == 10.0
    assert dwell["network_occurrence_count"] == 3
    assert dwell["slowness_ratio"] == 1.5
