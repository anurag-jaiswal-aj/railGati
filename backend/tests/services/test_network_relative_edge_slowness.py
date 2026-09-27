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
    db_session.add_all([t1, t2, t_empty, t_repeated])
    db_session.flush()

    stations = []
    for code in ["A", "B", "C", "D"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    # Target Train: 15905 (A -> B -> C -> D)
    # A->B: dep 10:00, arr 11:00 (60m)
    # B->C: dep 11:30, arr 12:00 (30m)
    # C->D: dep 23:30, arr 00:30 (60m, cross-midnight)
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

    # Peer Train: 15906 (A -> B -> C -> D)
    # A->B: dep 10:00, arr 10:20 (20m) -- makes target slower (avg 40m, ratio 1.5)
    # B->C: dep 12:00, arr 12:30 (30m) -- target same (avg 30m, ratio 1.0)
    # C->D: dep 13:00, arr 15:00 (120m) -- makes target faster (avg 90m, ratio 0.66)
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

    # Train Repeated: 04853 (A -> B -> C -> A -> B)
    # A->B (seq 1->2): dep 10:00, arr 11:00 (60m). Avg A->B = 60m (only this train for this test). Ratio = 1.0.
    # But wait, let's make a peer to create ratio > 1.0
    # Let's say Peer 15906 also does A->B in 20m. Avg A->B = (60 + 20 + 20) / 3 = 33.3m
    # A->B (seq 4->5): dep 14:00, arr 14:20 (20m).
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

    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))
    db_session.commit()
    return snapshot, t1, s_map


def test_calculate_train_relative_edge_slowness(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "15905")
    assert result["train_number"] == "15905"
    assert result["timetable_snapshot_id"] == 2

    # Expected averages:
    # A->B: 15905 (60m), 15906 (20m), 04853 (60m), 04853 (20m) -> Avg = (60+20+60+20)/4 = 40m
    # Ratio A->B = 60 / 40 = 1.5 (> 1.0) -> SHOULD BE RETURNED

    # B->C: 15905 (30m), 15906 (30m), 04853 (60m) -> Avg = 120/3 = 40m
    # Ratio B->C = 30 / 40 = 0.75 (< 1.0) -> EXCLUDED

    # C->D: 15905 (60m), 15906 (120m) -> Avg = 180/2 = 90m
    # Ratio C->D = 60 / 90 = 0.66 (< 1.0) -> EXCLUDED

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

    # Expected A->B Avg = 40m
    # 04853 A->B seq 1->2 is 60m. Ratio = 1.5 (> 1.0)
    # 04853 A->B seq 4->5 is 20m. Ratio = 0.5 (< 1.0)

    # 04853 B->C seq 2->3 is 60m. Avg = 40m. Ratio = 1.5 (> 1.0)
    # 04853 C->A seq 3->4 is 15m. Avg = 15m. Ratio = 1.0 (excluded)

    assert len(result["slow_edges"]) == 2

    # Should be sorted by ratio DESC, then seq ASC
    # Ratio A->B = 1.5, Ratio B->C = 1.5. Target seq A->B is 1, target seq B->C is 2.
    assert result["slow_edges"][0]["target_stop_sequence"] == 1
    assert result["slow_edges"][0]["source_station_code"] == "A"
    assert result["slow_edges"][0]["destination_station_code"] == "B"
    assert result["slow_edges"][0]["slowness_ratio"] == 1.5

    assert result["slow_edges"][1]["target_stop_sequence"] == 2
    assert result["slow_edges"][1]["source_station_code"] == "B"
    assert result["slow_edges"][1]["destination_station_code"] == "C"
    assert result["slow_edges"][1]["slowness_ratio"] == 1.5


def test_calculate_unknown_train(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_relative_edge_slowness(db_session, 2, "00000")


def test_calculate_empty_edges(db_session: Session, setup_service_data: typing.Any) -> None:
    result = calculate_train_relative_edge_slowness(db_session, 2, "99999")
    assert result["slow_edges"] == []
