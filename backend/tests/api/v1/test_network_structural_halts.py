import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation


@pytest.fixture
def setup_structural_halts_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    train = Train(id=1, number="15905")
    db_session.add(train)
    
    train_two_stop = Train(id=2, number="12301")
    db_session.add(train_two_stop)
    db_session.flush()

    # Create dummy stations
    stations = []
    for code in ["CAPE", "DGR", "BZA", "NJP", "GHY", "DBRG", "TNY", "ABC", "XYZ", "NULL_ARR", "NULL_DEP", "START", "END"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    # Add observations for train 15905
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations 
        (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time, source_day)
        VALUES 
        (2, 1, :s1, 1, NULL, '10:00:00', 1),                -- Origin
        (2, 1, :s2, 2, '12:00:00', '12:40:00', 1),          -- 40 min dwell
        (2, 1, :s3, 3, '14:00:00', '14:20:00', 1),          -- 20 min dwell
        (2, 1, :s4, 4, '23:55:00', '00:10:00', 1),          -- 15 min dwell cross-midnight
        (2, 1, :s5, 5, '04:00:00', '04:15:00', 2),          -- 15 min dwell
        (2, 1, :s7, 6, '06:00:00', '06:00:00', 2),          -- 0 min dwell
        (2, 1, :s_abc, 7, '07:00:00', '07:15:00', 2),       -- 15 min dwell tie ABC
        (2, 1, :s_xyz, 8, '08:00:00', '08:15:00', 2),       -- 15 min dwell tie XYZ
        (2, 1, :s_null_arr, 9, NULL, '09:00:00', 2),        -- Missing arrival
        (2, 1, :s_null_dep, 10, '10:00:00', NULL, 2),       -- Missing departure
        (2, 1, :s6, 11, '11:00:00', NULL, 2)                -- Destination
    """),
        {
            "s1": s_map["CAPE"],
            "s2": s_map["DGR"],
            "s3": s_map["BZA"],
            "s4": s_map["NJP"],
            "s5": s_map["GHY"],
            "s6": s_map["DBRG"],
            "s7": s_map["TNY"],
            "s_abc": s_map["ABC"],
            "s_xyz": s_map["XYZ"],
            "s_null_arr": s_map["NULL_ARR"],
            "s_null_dep": s_map["NULL_DEP"],
        },
    )

    # Train 12301 (2 stops only)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations 
        (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time, source_day)
        VALUES 
        (2, 2, :start, 1, NULL, '10:00:00', 1),             -- Origin
        (2, 2, :end, 2, '14:00:00', NULL, 1)                -- Destination
    """),
        {
            "start": s_map["START"],
            "end": s_map["END"],
        },
    )

    # Needs a TrainObservation in the snapshot to satisfy the `get_active_timetable_snapshot_id` check
    db_session.execute(
        text(
            "INSERT INTO station_observations (snapshot_id, station_id, name) VALUES (2, :s1, 'CAPE')"
        ),
        {"s1": s_map["CAPE"]},
    )
    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))
    db_session.add(TrainObservation(snapshot_id=2, train_id=2, name="Test"))

    db_session.commit()
    return snapshot, train, s_map


def test_get_structural_halts_success(
    client: typing.Any, setup_structural_halts_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/15905/structural-halts")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "15905"
    assert data["timetable_snapshot_id"] == 2
    
    # 40m, 20m, 15m, 15m, 15m, 15m, 0m -> 7 qualifying intermediate stops
    assert len(data["halts"]) == 7

    # Exclusions explicitly checked by the resulting array length/contents:
    # CAPE (Origin) excluded
    # DBRG (Destination) excluded
    # NULL_ARR (Missing arrival) excluded
    # NULL_DEP (Missing departure) excluded
    station_codes = [h["station_code"] for h in data["halts"]]
    assert "CAPE" not in station_codes
    assert "DBRG" not in station_codes
    assert "NULL_ARR" not in station_codes
    assert "NULL_DEP" not in station_codes

    # Check ordering
    assert data["halts"][0]["station_code"] == "DGR"
    assert data["halts"][0]["dwell_minutes"] == 40.0

    assert data["halts"][1]["station_code"] == "BZA"
    assert data["halts"][1]["dwell_minutes"] == 20.0

    # Tie-breaks for 15.0 minutes (ABC, GHY, NJP, XYZ sorted alphabetically)
    assert data["halts"][2]["station_code"] == "ABC"
    assert data["halts"][2]["dwell_minutes"] == 15.0

    assert data["halts"][3]["station_code"] == "GHY"
    assert data["halts"][3]["dwell_minutes"] == 15.0

    assert data["halts"][4]["station_code"] == "NJP"
    assert data["halts"][4]["dwell_minutes"] == 15.0
    
    assert data["halts"][5]["station_code"] == "XYZ"
    assert data["halts"][5]["dwell_minutes"] == 15.0

    # 0 minute dwell
    assert data["halts"][6]["station_code"] == "TNY"
    assert data["halts"][6]["dwell_minutes"] == 0.0


def test_get_structural_halts_two_stops(
    client: typing.Any, setup_structural_halts_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/12301/structural-halts")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12301"
    assert data["timetable_snapshot_id"] == 2
    assert len(data["halts"]) == 0


def test_get_structural_halts_unknown_train(
    client: typing.Any, setup_structural_halts_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/99999/structural-halts")
    assert response.status_code == 404
