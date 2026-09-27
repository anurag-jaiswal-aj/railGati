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
    db_session.flush()

    # Create dummy stations
    stations = []
    for code in ["CAPE", "DGR", "BZA", "NJP", "GHY", "DBRG", "TNY"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    # Add observations for train 15905
    # Sequence 1: CAPE (Origin)
    db_session.execute(
        text("""
        INSERT INTO train_stop_observations 
        (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time, source_day)
        VALUES 
        (2, 1, :s1, 1, NULL, '10:00:00', 1),
        (2, 1, :s2, 2, '12:00:00', '12:40:00', 1),  -- 40 min dwell
        (2, 1, :s3, 3, '14:00:00', '14:20:00', 1),  -- 20 min dwell
        (2, 1, :s4, 4, '23:55:00', '00:10:00', 1),  -- 15 min dwell cross-midnight
        (2, 1, :s5, 5, '04:00:00', '04:15:00', 2),  -- 15 min dwell
        (2, 1, :s7, 6, '06:00:00', '06:00:00', 2),  -- 0 min dwell
        (2, 1, :s6, 7, '08:00:00', NULL, 2)         -- Destination
    """),
        {
            "s1": s_map["CAPE"],
            "s2": s_map["DGR"],
            "s3": s_map["BZA"],
            "s4": s_map["NJP"],
            "s5": s_map["GHY"],
            "s6": s_map["DBRG"],
            "s7": s_map["TNY"],
        },
    )

    # Needs a TrainObservation in the snapshot to satisfy the `get_active_timetable_snapshot_id` check
    # Wait, get_active_timetable_snapshot_id checks station_observations!
    db_session.execute(
        text(
            "INSERT INTO station_observations (snapshot_id, station_id, name) VALUES (2, :s1, 'CAPE')"
        ),
        {"s1": s_map["CAPE"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) VALUES (2, 1, :s1, 8)"
        ),
        {"s1": s_map["CAPE"]},
    )
    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))

    db_session.commit()
    return snapshot, train, s_map


def test_get_structural_halts_success(client: typing.Any, setup_structural_halts_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/15905/structural-halts")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "15905"
    assert data["timetable_snapshot_id"] == 2
    assert len(data["halts"]) == 5

    # Check ordering
    assert data["halts"][0]["station_code"] == "DGR"
    assert data["halts"][0]["dwell_minutes"] == 40.0

    assert data["halts"][1]["station_code"] == "BZA"
    assert data["halts"][1]["dwell_minutes"] == 20.0

    # NJP cross midnight
    assert data["halts"][2]["station_code"] == "GHY"
    assert data["halts"][2]["dwell_minutes"] == 15.0

    assert data["halts"][3]["station_code"] == "NJP"
    assert data["halts"][3]["dwell_minutes"] == 15.0


def test_get_structural_halts_unknown_train(client: typing.Any, setup_structural_halts_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/99999/structural-halts")
    assert response.status_code == 404
