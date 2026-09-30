import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainStopObservation


@pytest.fixture
def api_junction_fixtures(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM railway_network_edges"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.commit()

    source = DataSource(name="Source API 63", publisher="pub", url="url", license="mit")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stn_codes = ["API_S", "API_A", "API_B", "API_C"]
    stations = {}
    for code in stn_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    from railgati.models.station import StationObservation
    for code in stn_codes:
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap_id, name=code))
    db_session.commit()

    db_session.execute(text("INSERT INTO railway_network_edges (from_station_id, to_station_id, timetable_snapshot_id, train_count) VALUES (:f, :t, :s, 1)"), [
        {"f": stations["API_A"].id, "t": stations["API_S"].id, "s": snap_id},
        {"f": stations["API_B"].id, "t": stations["API_S"].id, "s": snap_id},
        {"f": stations["API_C"].id, "t": stations["API_S"].id, "s": snap_id},
    ])
    db_session.commit()

    from railgati.models.train import TrainObservation
    def add_train(tr_num: str, path: list[str]):
        tr = Train(number=tr_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(TrainObservation(train_id=tr.id, snapshot_id=snap_id, name=f"Train {tr_num}", type="EXP"))
        for i, code in enumerate(path, 1):
            tso = TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[code].id,
                stop_sequence=i
            )
            db_session.add(tso)
        db_session.commit()

    add_train("TR_1", ["API_A", "API_S", "API_B"])

    return None

def test_api_junction_success(client: TestClient, api_junction_fixtures: None) -> None:
    res = client.get("/api/v1/network/stations/API_S/junction-through-service")
    assert res.status_code == 200
    data = res.json()
    assert data["station_code"] == "API_S"
    assert data["station_name"] == "API_S"
    assert data["neighbor_count"] == 3
    assert data["possible_neighbor_pairs"] == 3
    assert data["served_neighbor_pairs"] == 1
    assert data["through_service_pair_ratio"] == round(1/3, 4)
    assert len(data["served_pairs"]) == 1
    assert data["served_pairs"][0]["neighbor_a"] == "API_A"
    assert data["served_pairs"][0]["neighbor_b"] == "API_B"
    assert data["served_pairs"][0]["qualifying_train_count"] == 1

def test_api_junction_unknown(client: TestClient, api_junction_fixtures: None) -> None:
    res = client.get("/api/v1/network/stations/UNKNOWN/junction-through-service")
    assert res.status_code == 404

def test_api_junction_k1(client: TestClient, api_junction_fixtures: None) -> None:
    res = client.get("/api/v1/network/stations/API_A/junction-through-service")
    assert res.status_code == 400
    assert "degree = 1" in res.json()["detail"]
