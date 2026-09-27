import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation


@pytest.fixture
def setup_api_data(db_session: Session) -> typing.Any:
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

    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 1, :s_a, 1, NULL, '10:00:00'), (2, 1, :s_b, 2, '11:00:00', '11:30:00'), (2, 1, :s_c, 3, '12:00:00', '23:30:00'), (2, 1, :s_d, 4, '00:30:00', NULL)"
        ),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 2, :s_a, 1, NULL, '10:00:00'), (2, 2, :s_b, 2, '10:20:00', '12:00:00'), (2, 2, :s_c, 3, '12:30:00', '13:00:00'), (2, 2, :s_d, 4, '15:00:00', NULL)"
        ),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 4, :s_a, 1, NULL, '10:00:00'), (2, 4, :s_b, 2, '11:00:00', '12:00:00'), (2, 4, :s_c, 3, '13:00:00', '13:30:00'), (2, 4, :s_a, 4, '13:45:00', '14:00:00'), (2, 4, :s_b, 5, '14:20:00', NULL)"
        ),
        {"s_a": s_map["A"], "s_b": s_map["B"], "s_c": s_map["C"], "s_d": s_map["D"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 3, :s_a, 1, NULL, '10:00:00'), (2, 3, :s_c, 2, '11:00:00', NULL)"
        ),
        {"s_a": s_map["A"], "s_c": s_map["C"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 5, :s_b, 1, NULL, '10:00:00'), (2, 5, :s_d, 2, '10:00:00', NULL)"
        ),
        {"s_b": s_map["B"], "s_d": s_map["D"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 6, :s_c, 1, NULL, NULL), (2, 6, :s_d, 2, '10:00:00', NULL)"
        ),
        {"s_c": s_map["C"], "s_d": s_map["D"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 7, :s_a, 1, NULL, '23:30:00'), (2, 7, :s_d, 2, '00:30:00', NULL)"
        ),
        {"s_a": s_map["A"], "s_d": s_map["D"]},
    )
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, 2, :s_a, 5, NULL, '23:30:00'), (2, 2, :s_d, 6, '23:50:00', NULL)"
        ),
        {"s_a": s_map["A"], "s_d": s_map["D"]},
    )

    db_session.execute(
        text(
            "INSERT INTO station_observations (snapshot_id, station_id, name) VALUES (2, :s1, 'TEST')"
        ),
        {"s1": s_map["A"]},
    )
    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))

    db_session.commit()
    return snapshot, t1, s_map


def test_api_relative_edge_slowness_success(client: typing.Any, setup_api_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/15905/relative-edge-slowness")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "15905"
    assert data["timetable_snapshot_id"] == 2
    assert len(data["slow_edges"]) == 1
    edge = data["slow_edges"][0]
    assert edge["source_station_code"] == "A"
    assert edge["destination_station_code"] == "B"
    assert edge["slowness_ratio"] == 1.5


def test_api_relative_edge_slowness_repeated(
    client: typing.Any, setup_api_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/04853/relative-edge-slowness")
    assert response.status_code == 200
    data = response.json()
    assert len(data["slow_edges"]) == 2
    assert data["slow_edges"][0]["target_stop_sequence"] == 1
    assert data["slow_edges"][1]["target_stop_sequence"] == 2


def test_api_relative_edge_slowness_unknown(client: typing.Any, setup_api_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/00000/relative-edge-slowness")
    assert response.status_code == 404


def test_api_relative_edge_slowness_empty(client: typing.Any, setup_api_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/99999/relative-edge-slowness")
    assert response.status_code == 200
    assert response.json()["slow_edges"] == []
