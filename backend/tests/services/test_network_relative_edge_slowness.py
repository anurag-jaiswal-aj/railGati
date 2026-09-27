import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation
from railgati.services.network import calculate_train_relative_edge_slowness


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

    # 15905 (Target)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 1, :s_a, 1, NULL, '10:00:00'),
        (2, 1, :s_b, 2, '11:00:00', '11:30:00'),
        (2, 1, :s_c, 3, '12:00:00', '23:30:00'),
        (2, 1, :s_d, 4, '00:30:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # 15906 (Peer)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 2, :s_a, 1, NULL, '10:00:00'),
        (2, 2, :s_b, 2, '10:20:00', '12:00:00'),
        (2, 2, :s_c, 3, '12:30:00', '13:00:00'),
        (2, 2, :s_d, 4, '15:00:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # 04853 (Repeated)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 4, :s_a, 1, NULL, '10:00:00'),
        (2, 4, :s_b, 2, '11:00:00', '12:00:00'),
        (2, 4, :s_c, 3, '13:00:00', '13:30:00'),
        (2, 4, :s_a, 4, '13:45:00', '14:00:00'),
        (2, 4, :s_b, 5, '14:20:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # 99999 (Valid train, no qualifying slow edges - all ratios = 1.0)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 3, :s_a, 1, NULL, '10:00:00'),
        (2, 3, :s_c, 2, '11:00:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # ZEROAVG (Valid train, zero average)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 5, :s_b, 1, NULL, '10:00:00'),
        (2, 5, :s_d, 2, '10:00:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # MISSING (Valid train, missing timings)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 6, :s_c, 1, NULL, NULL),
        (2, 6, :s_d, 2, '10:00:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # MIDNIGHT
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 7, :s_a, 1, NULL, '23:30:00'),
        (2, 7, :s_d, 2, '00:30:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    # Peer for MIDNIGHT to make it slow
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time)
        VALUES 
        (2, 2, :s_a, 5, NULL, '23:30:00'),
        (2, 2, :s_d, 6, '23:50:00', NULL)
        """),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )

    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))
    db_session.commit()
    return snapshot, t1, s_map


def test_calculate_train_relative_edge_slowness(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "15905")
    assert result["train_number"] == "15905"

    assert len(result["slow_edges"]) == 1
    edge = result["slow_edges"][0]
    assert edge["source_station_code"] == "A"
    assert edge["destination_station_code"] == "B"
    assert edge["target_duration_minutes"] == 60.0
    assert edge["network_average_minutes"] == 40.0
    assert edge["network_occurrence_count"] == 4
    assert edge["slowness_ratio"] == 1.5


def test_calculate_repeated_edges(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "04853")
    assert result["train_number"] == "04853"

    # A->B avg = 40m, count = 4
    # 04853 A->B seq 1: 60m (ratio 1.5)
    # 04853 A->B seq 4: 20m (ratio 0.5) - omitted

    assert len(result["slow_edges"]) == 2

    assert result["slow_edges"][0]["target_stop_sequence"] == 1
    assert result["slow_edges"][0]["source_station_code"] == "A"
    assert result["slow_edges"][0]["destination_station_code"] == "B"
    assert result["slow_edges"][0]["network_occurrence_count"] == 4
    assert result["slow_edges"][0]["slowness_ratio"] == 1.5

    assert result["slow_edges"][1]["target_stop_sequence"] == 2
    assert result["slow_edges"][1]["source_station_code"] == "B"
    assert result["slow_edges"][1]["destination_station_code"] == "C"
    assert result["slow_edges"][1]["network_occurrence_count"] == 3
    assert result["slow_edges"][1]["slowness_ratio"] == 1.5


def test_calculate_unknown_train(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_relative_edge_slowness(db_session, 2, "00000")


def test_calculate_empty_edges(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "99999")
    assert result["slow_edges"] == []


def test_calculate_zero_average(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "ZEROAVG")
    assert result["slow_edges"] == []


def test_calculate_missing_timings(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "MISSING")
    assert result["slow_edges"] == []


def test_calculate_cross_midnight(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "MIDNIGHT")
    assert len(result["slow_edges"]) == 1
    edge = result["slow_edges"][0]
    assert edge["source_station_code"] == "A"
    assert edge["destination_station_code"] == "D"
    assert edge["target_duration_minutes"] == 60.0
    assert edge["network_average_minutes"] == 40.0
    assert edge["network_occurrence_count"] == 2
    assert edge["slowness_ratio"] == 1.5
