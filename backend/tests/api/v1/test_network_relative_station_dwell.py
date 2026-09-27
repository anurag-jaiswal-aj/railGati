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

    db_session.add_all([t1, t2, t_empty, t_repeated])
    db_session.flush()

    stations = []
    for code in ["A", "B", "C", "D"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    def add_stop(train_id, st_code, seq, arr, dep):
        db_session.execute(
            text(
                "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence, arrival_time, departure_time) VALUES (2, :t, :s, :seq, :a, :d)"
            ),
            {"t": train_id, "s": s_map[st_code], "seq": seq, "a": arr, "d": dep},
        )

    add_stop(1, "A", 1, None, "10:00:00")
    add_stop(1, "B", 2, "11:00:00", "12:00:00")
    add_stop(1, "C", 3, "13:00:00", None)

    add_stop(2, "A", 1, None, "10:00:00")
    add_stop(2, "B", 2, "11:10:00", "11:30:00")
    add_stop(2, "C", 3, "13:00:00", None)

    add_stop(4, "A", 1, None, "10:00:00")
    add_stop(4, "B", 2, "11:00:00", "12:00:00")
    add_stop(4, "C", 3, "13:00:00", "13:10:00")
    add_stop(4, "B", 4, "14:00:00", "14:20:00")
    add_stop(4, "D", 5, "15:00:00", None)

    add_stop(3, "A", 1, None, "10:00:00")
    add_stop(3, "B", 2, "11:00:00", "11:20:00")
    add_stop(3, "C", 3, "12:00:00", None)

    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))
    db_session.commit()
    return snapshot, t1, s_map


def test_api_relative_station_dwell_success(client: typing.Any, setup_api_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/15905/relative-station-dwell")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "15905"
    assert data["timetable_snapshot_id"] == 2
    assert len(data["relative_dwells"]) == 1
    dwell = data["relative_dwells"][0]
    assert dwell["station_code"] == "B"
    assert dwell["slowness_ratio"] == 60.0 / 36.0


def test_api_relative_station_dwell_repeated(
    client: typing.Any, setup_api_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/04853/relative-station-dwell")
    assert response.status_code == 200
    data = response.json()
    assert len(data["relative_dwells"]) == 1
    assert data["relative_dwells"][0]["target_stop_sequence"] == 2


def test_api_relative_station_dwell_unknown(client: typing.Any, setup_api_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/00000/relative-station-dwell")
    assert response.status_code == 404


def test_api_relative_station_dwell_empty(client: typing.Any, setup_api_data: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/99999/relative-station-dwell")
    assert response.status_code == 200
    assert response.json()["relative_dwells"] == []
